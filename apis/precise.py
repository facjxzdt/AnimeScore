#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多源交叉验证的精确动画搜索
支持Bangumi、AniList、MAL(Jikan API)多源搜索并交叉验证
"""

import asyncio
import re
import unicodedata
import json
import os
from functools import lru_cache
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

import httpx

from data.config import work_dir

try:
    from rapidfuzz import fuzz as rapidfuzz_fuzz
except Exception:
    rapidfuzz_fuzz = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

_EMBEDDING_MODEL = None

try:
    from apis.anikore import Anikore
except Exception:
    Anikore = None

try:
    from apis.filmarks import Filmarks
except Exception:
    Filmarks = None

_ANK_CLIENT = None
_FM_CLIENT = None
ENABLE_ANIKORE = False

try:
    from utils.ext_linker import lookup_ext_ids
except Exception:
    lookup_ext_ids = None


_ASYNC_TIMEOUT = float(os.getenv("PRECISE_HTTP_TIMEOUT", "10"))
_ASYNC_MAX_CONNECTIONS = int(os.getenv("PRECISE_HTTP_MAX_CONNECTIONS", "50"))
_ASYNC_MAX_KEEPALIVE = int(os.getenv("PRECISE_HTTP_MAX_KEEPALIVE", "20"))
_ASYNC_QUERY_CONCURRENCY = int(os.getenv("PRECISE_QUERY_CONCURRENCY", "4"))
_SEARCH_SEM_BY_LOOP: Dict[int, asyncio.Semaphore] = {}


def _build_async_client() -> httpx.AsyncClient:
    limits = httpx.Limits(
        max_connections=_ASYNC_MAX_CONNECTIONS,
        max_keepalive_connections=_ASYNC_MAX_KEEPALIVE,
    )
    timeout = httpx.Timeout(_ASYNC_TIMEOUT)
    return httpx.AsyncClient(limits=limits, timeout=timeout)


def _get_search_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    key = id(loop)
    sem = _SEARCH_SEM_BY_LOOP.get(key)
    if sem is None:
        sem = asyncio.Semaphore(_ASYNC_QUERY_CONCURRENCY)
        _SEARCH_SEM_BY_LOOP[key] = sem
    return sem


@dataclass
class AnimeInfo:
    """动画信息数据类"""

    bgm_id: Optional[str] = None
    mal_id: Optional[str] = None
    anilist_id: Optional[str] = None

    name: str = ""
    name_cn: str = ""
    name_jp: str = ""

    year: Optional[int] = None
    month: Optional[int] = None
    studio: str = ""
    director: str = ""
    source: str = ""  # 原作类型：漫画、轻小说、原创等

    bgm_score: Optional[float] = None
    mal_score: Optional[float] = None
    anilist_score: Optional[float] = None

    summary: str = ""
    confidence: float = 0.0  # 匹配置信度

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "bgm_id": self.bgm_id,
            "mal_id": self.mal_id,
            "anilist_id": self.anilist_id,
            "name": self.name,
            "name_cn": self.name_cn,
            "name_jp": self.name_jp,
            "year": self.year,
            "month": self.month,
            "studio": self.studio,
            "director": self.director,
            "source": self.source,
            "bgm_score": self.bgm_score,
            "mal_score": self.mal_score,
            "anilist_score": self.anilist_score,
            "summary": self.summary,
            "confidence": self.confidence,
        }

    def get_all_names(self) -> List[str]:
        """获取所有非空名称"""
        names = []
        if self.name:
            names.append(self.name)
        if self.name_cn:
            names.append(self.name_cn)
        if self.name_jp:
            names.append(self.name_jp)
        return names


def _has_japanese(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if (
            0x3040 <= code <= 0x309F  # Hiragana
            or 0x30A0 <= code <= 0x30FF  # Katakana
            or 0x4E00 <= code <= 0x9FFF  # CJK Unified
        ):
            return True
    return False


def _normalize_title(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).lower()
    roman_map = {
        "ⅰ": "1",
        "ⅱ": "2",
        "ⅲ": "3",
        "ⅳ": "4",
        "ⅴ": "5",
        "ⅵ": "6",
        "ⅶ": "7",
        "ⅷ": "8",
        "ⅸ": "9",
        "ⅹ": "10",
        "Ⅰ": "1",
        "Ⅱ": "2",
        "Ⅲ": "3",
        "Ⅳ": "4",
        "Ⅴ": "5",
        "Ⅵ": "6",
        "Ⅶ": "7",
        "Ⅷ": "8",
        "Ⅸ": "9",
        "Ⅹ": "10",
    }
    for k, v in roman_map.items():
        t = t.replace(k, f" {v} ")
    t = re.sub(r"\[.*?\]|\(.*?\)|\{.*?\}|<.*?>", " ", t)
    t = re.sub(r"(season|part|cour)\s*\d+", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(s\d+|s\d+\s*e\d+|ova|oad|sp|special|movie|tv)\b", " ", t)
    t = re.sub(r"\b(ii|iii|iv|v|vi|vii|viii|ix|x)\b", " ", t)
    t = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tokenize_title(text: str) -> List[str]:
    n = _normalize_title(text)
    if not n:
        return []
    tokens = n.split()
    if len(tokens) == 1 and _has_japanese(tokens[0]) and len(tokens[0]) > 2:
        s = tokens[0]
        tokens = [s[i : i + 2] for i in range(len(s) - 1)]
    return tokens


def _token_overlap_score(a: str, b: str) -> float:
    ta = _tokenize_title(a)
    tb = _tokenize_title(b)
    if not ta or not tb:
        return 0.0
    sa = set(ta)
    sb = set(tb)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _contains_all_tokens(short_title: str, long_title: str) -> bool:
    short_tokens = _tokenize_title(short_title)
    long_tokens = _tokenize_title(long_title)
    if not short_tokens or not long_tokens:
        return False
    return set(short_tokens).issubset(set(long_tokens))




def _ngram_jaccard(a: str, b: str, n: int = 2) -> float:
    if not a or not b:
        return 0.0
    def ngrams(s: str) -> Set[str]:
        if len(s) < n:
            return {s}
        return {s[i : i + n] for i in range(len(s) - n + 1)}
    na = ngrams(a)
    nb = ngrams(b)
    if not na or not nb:
        return 0.0
    return len(na & nb) / len(na | nb)


def _similarity_score(a: str, b: str, mode: str = "normal") -> float:
    if not a or not b:
        return 0.0
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    jac = _ngram_jaccard(na, nb, n=2)
    tok = _token_overlap_score(a, b)
    rf = 0.0
    if rapidfuzz_fuzz:
        try:
            rf = rapidfuzz_fuzz.token_set_ratio(na, nb) / 100.0
        except Exception:
            rf = 0.0
    scores = [seq, jac, tok, rf]
    scores.sort()
    if mode == "strict":
        base_score = scores[-1] * 0.6 + scores[-2] * 0.3 + scores[-3] * 0.1
    elif mode == "recall":
        base_score = scores[-1] * 0.55 + scores[-2] * 0.45
    else:
        base_score = scores[-1] * 0.65 + scores[-2] * 0.35

    # Optional embedding similarity (high accuracy, higher compute)
    emb_score = _embedding_similarity(na, nb)
    if emb_score is not None:
        return max(base_score, emb_score)
    return base_score


def _get_embedding_model():
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL
    if SentenceTransformer is None:
        return None
    try:
        # Use a small model; must be pre-downloaded to avoid long startup
        _EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _EMBEDDING_MODEL = None
    return _EMBEDDING_MODEL


@lru_cache(maxsize=2048)
def _embed_text(text: str):
    model = _get_embedding_model()
    if model is None:
        return None
    try:
        emb = model.encode([text], normalize_embeddings=True)
        return emb[0]
    except Exception:
        return None


def _embedding_similarity(a: str, b: str) -> Optional[float]:
    model = _get_embedding_model()
    if model is None:
        return None
    ea = _embed_text(a)
    eb = _embed_text(b)
    if ea is None or eb is None:
        return None
    try:
        # Cosine similarity (embeddings are normalized)
        return float((ea * eb).sum())
    except Exception:
        return None



def _get_anikore_client():
    global _ANK_CLIENT
    if _ANK_CLIENT is not None:
        return _ANK_CLIENT
    if Anikore is None:
        return None
    try:
        _ANK_CLIENT = Anikore()
    except Exception:
        _ANK_CLIENT = None
    return _ANK_CLIENT


def _get_filmarks_client():
    global _FM_CLIENT
    if _FM_CLIENT is not None:
        return _FM_CLIENT
    if Filmarks is None:
        return None
    try:
        _FM_CLIENT = Filmarks()
    except Exception:
        _FM_CLIENT = None
    return _FM_CLIENT


def _extra_title_candidates(name: str, name_cn: str, name_jp: str) -> List[str]:
    # Prefer JP/CJK titles first; many source sites match these better than romaji.
    raw = [name_jp, name_cn, name]
    seen = set()
    candidates: List[str] = []
    for t in raw:
        if not t:
            continue
        norm = _normalize_title(t)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        candidates.append(t)
    return candidates


def _anikore_query_variants(titles: List[str]) -> List[str]:
    variants: List[str] = []
    seen = set()
    for t in titles:
        if not t:
            continue
        pool = [t]
        # Remove common punctuation for JP/CJK titles.
        t_no_punct = re.sub(r"[!！?？・·:：/／\-—～~\s]+", "", t)
        if t_no_punct and t_no_punct != t:
            pool.append(t_no_punct)
        # Extract Japanese-only segment, often works better for Anikore search.
        jp_only = "".join(ch for ch in t if _has_japanese(ch))
        if jp_only and jp_only != t and len(jp_only) >= 2:
            pool.append(jp_only)
        # If title is long, try a shorter core keyword.
        if len(jp_only) >= 4:
            pool.append(jp_only[-4:])
            pool.append(jp_only[-5:])
        for q in pool:
            nq = _normalize_title(q)
            if not nq or nq in seen:
                continue
            seen.add(nq)
            variants.append(q)
    return variants[:12]


def _extract_numeric_score(value: object, min_value: float = 0.0, max_value: float = 10.0) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    try:
        score = float(m.group(1))
    except Exception:
        return None
    if score < min_value or score > max_value:
        return None
    return score


@lru_cache(maxsize=1)
def _load_local_score_index() -> Dict[str, Dict[str, dict]]:
    by_bgm: Dict[str, dict] = {}
    by_mal: Dict[str, dict] = {}
    by_title: Dict[str, dict] = {}
    paths = [
        os.path.join(work_dir, "data", "jsons", "score_sorted.json"),
        os.path.join(work_dir, "data", "jsons", "sub_score_sorted.json"),
    ]
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        for k, v in data.items():
            if not isinstance(v, dict) or k == "total":
                continue
            bgm_id = v.get("bgm_id") or (v.get("ids") or {}).get("bgm_id")
            mal_id = (v.get("ids") or {}).get("mal_id")
            if bgm_id:
                by_bgm[str(bgm_id)] = v
            if mal_id:
                by_mal[str(mal_id)] = v
            for t in [k, v.get("name"), v.get("name_cn"), v.get("name_jp")]:
                if not t:
                    continue
                nt = _normalize_title(str(t))
                if nt and nt not in by_title:
                    by_title[nt] = v
    return {"bgm": by_bgm, "mal": by_mal, "title": by_title}


def _lookup_local_score(item: dict) -> Optional[dict]:
    idx = _load_local_score_index()
    bgm_id = item.get("bgm_id")
    mal_id = item.get("mal_id")
    if bgm_id and str(bgm_id) in idx["bgm"]:
        return idx["bgm"][str(bgm_id)]
    if mal_id and str(mal_id) in idx["mal"]:
        return idx["mal"][str(mal_id)]
    for t in [item.get("name_jp"), item.get("name"), item.get("name_cn")]:
        if not t:
            continue
        nt = _normalize_title(str(t))
        if nt and nt in idx["title"]:
            return idx["title"][nt]
    return None


def _merge_local_extra_scores(item: dict, debug: Optional[dict] = None) -> None:
    local = _lookup_local_score(item)
    if not local:
        if debug is not None:
            debug["local_fallback"] = {"matched": False}
        return
    if debug is not None:
        debug["local_fallback"] = {"matched": True}
    local_ids = local.get("ids") or {}
    # Anikore channel is disabled intentionally.
    if item.get("fm_score") is None:
        parsed_fm = _extract_numeric_score(local.get("fm_score"), min_value=0.0, max_value=10.0)
        if parsed_fm is not None:
            item["fm_score"] = parsed_fm
            if debug is not None:
                debug["local_fallback"]["fm_score"] = parsed_fm


@lru_cache(maxsize=1024)
def _fetch_extra_scores(name: str, name_cn: str, name_jp: str) -> dict:
    result = {}
    candidates = _extra_title_candidates(name, name_cn, name_jp)
    if not candidates:
        return result
    queries = _anikore_query_variants(candidates)

    ank = _get_anikore_client()
    if ank and ENABLE_ANIKORE:
        for title in queries:
            try:
                ank_id = ank.get_ani_id(title)
                if ank_id and ank_id != "Error":
                    score = ank.get_ani_score(ank_id)
                    if score and score != "None":
                        parsed = _extract_numeric_score(score, min_value=0.0, max_value=5.0)
                        if parsed is not None:
                            result["ank_score"] = round(2 * parsed, 2)
                            result["ank_id"] = str(ank_id)
                            break
            except Exception:
                continue

    fm = _get_filmarks_client()
    if fm:
        for title in candidates:
            try:
                fm_score = fm.get_fm_score(title)
                if fm_score and fm_score != "Error":
                    parsed = _extract_numeric_score(fm_score, min_value=0.0, max_value=5.0)
                    if parsed is not None:
                        result["fm_score"] = round(2 * parsed, 2)
                        break
            except Exception:
                continue

    return result


def _fetch_extra_scores_debug(name: str, name_cn: str, name_jp: str) -> Tuple[dict, dict]:
    result = {}
    base_titles = _extra_title_candidates(name, name_cn, name_jp)
    queries = _anikore_query_variants(base_titles)
    debug = {
        "titles": base_titles,
        "anikore_queries": queries,
        "anikore": {"enabled": ENABLE_ANIKORE, "attempts": [], "hit": False},
        "filmarks": {"attempts": [], "hit": False},
    }
    if not base_titles:
        return result, debug

    ank = _get_anikore_client()
    if ank and ENABLE_ANIKORE:
        for title in queries:
            attempt = {"title": title}
            try:
                ank_id = ank.get_ani_id(title)
                attempt["ank_id"] = ank_id
                if ank_id and ank_id != "Error":
                    raw = ank.get_ani_score(ank_id)
                    attempt["raw_score"] = raw
                    parsed = _extract_numeric_score(raw, min_value=0.0, max_value=5.0)
                    attempt["parsed"] = parsed
                    if parsed is not None:
                        result["ank_score"] = round(2 * parsed, 2)
                        result["ank_id"] = str(ank_id)
                        debug["anikore"]["hit"] = True
                        debug["anikore"]["selected"] = attempt
                        debug["anikore"]["attempts"].append(attempt)
                        break
                debug["anikore"]["attempts"].append(attempt)
            except Exception as e:
                attempt["error"] = str(e)
                debug["anikore"]["attempts"].append(attempt)
    elif not ENABLE_ANIKORE:
        debug["anikore"]["reason"] = "disabled"

    fm = _get_filmarks_client()
    if fm:
        for title in base_titles:
            attempt = {"title": title}
            try:
                raw = fm.get_fm_score(title)
                attempt["raw_score"] = raw
                parsed = _extract_numeric_score(raw, min_value=0.0, max_value=5.0)
                attempt["parsed"] = parsed
                if parsed is not None:
                    result["fm_score"] = round(2 * parsed, 2)
                    debug["filmarks"]["hit"] = True
                    debug["filmarks"]["selected"] = attempt
                    debug["filmarks"]["attempts"].append(attempt)
                    break
                debug["filmarks"]["attempts"].append(attempt)
            except Exception as e:
                attempt["error"] = str(e)
                debug["filmarks"]["attempts"].append(attempt)

    return result, debug


class BaseSearcher:
    """搜索器基类"""

    def __init__(self, name: str):
        self.name = name

    def _calculate_confidence(self, keyword: str, *titles: Optional[str]) -> float:
        max_ratio = 0.0
        for title in titles:
            if title:
                ratio = _similarity_score(keyword, title)
                max_ratio = max(max_ratio, ratio)
        return max_ratio




class BangumiSearcher(BaseSearcher):
    """Bangumi搜索器"""

    def __init__(self):
        super().__init__("Bangumi")
        self.api_base = "https://api.bgm.tv"
        self.headers = {"User-Agent": "precise-search/1.0"}

    def search(self, keyword: str, **filters) -> List[AnimeInfo]:
        """
        搜索Bangumi

        Args:
            keyword: 搜索关键词
            filters: 过滤条件 {year, studio, type, month}

        Returns:
            AnimeInfo列表
        """
        results = []
        try:
            url = f"{self.api_base}/v0/search/subjects"
            payload = {
                "keyword": keyword,
                "sort": "match",
                "filter": {"type": [2]},  # 2=动画
            }

            # 添加年份过滤
            if filters.get("year"):
                payload["filter"]["year"] = [filters["year"]]

            # 添加月份过滤
            if filters.get("month"):
                month_map = {
                    1: "1月",
                    2: "2月",
                    3: "3月",
                    4: "4月",
                    5: "5月",
                    6: "6月",
                    7: "7月",
                    8: "8月",
                    9: "9月",
                    10: "10月",
                    11: "11月",
                    12: "12月",
                }
                payload["filter"]["month"] = [[month_map[filters["month"]]]]

            response = httpx.post(
                url, headers=self.headers, json=payload, timeout=10
            )
            data = response.json()

            if "data" in data:
                for item in data["data"][:20]:  # 限制结果数量
                    info = AnimeInfo()
                    info.bgm_id = str(item.get("id"))
                    info.name = item.get("name", "")
                    info.name_cn = item.get("name_cn", "")

                    # 获取评分
                    if item.get("rating"):
                        info.bgm_score = item["rating"].get("score")

                    # 获取年份
                    if item.get("date"):
                        date_str = item["date"]
                        match = re.search(r"(\d{4})-(\d{2})", date_str)
                        if match:
                            info.year = int(match.group(1))
                            info.month = int(match.group(2))

                    # 获取制作信息
                    if item.get("infobox"):
                        for info_box in item["infobox"]:
                            key = info_box.get("key", "")
                            value = info_box.get("value", "")
                            if key == "动画制作":
                                info.studio = value
                            elif key == "监督":
                                info.director = value
                            elif key == "原作":
                                info.source = value

                    # 获取简介
                    info.summary = item.get("summary", "")[:200]

                    # 计算匹配度
                    info.confidence = self._calculate_confidence(
                        keyword, info.name, info.name_cn
                    )

                    results.append(info)

        except Exception as e:
            print(f"Bangumi搜索错误: {e}")

        return results

    async def asearch(
        self, client: httpx.AsyncClient, keyword: str, **filters
    ) -> List[AnimeInfo]:
        """异步搜索Bangumi"""
        results: List[AnimeInfo] = []
        try:
            url = f"{self.api_base}/v0/search/subjects"
            payload = {
                "keyword": keyword,
                "sort": "match",
                "filter": {"type": [2]},
            }

            if filters.get("year"):
                payload["filter"]["year"] = [filters["year"]]

            if filters.get("month"):
                month_map = {
                    1: "1月",
                    2: "2月",
                    3: "3月",
                    4: "4月",
                    5: "5月",
                    6: "6月",
                    7: "7月",
                    8: "8月",
                    9: "9月",
                    10: "10月",
                    11: "11月",
                    12: "12月",
                }
                payload["filter"]["month"] = [[month_map[filters["month"]]]]

            async with _get_search_semaphore():
                response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()

            for item in data.get("data", [])[:20]:
                info = AnimeInfo()
                info.bgm_id = str(item.get("id"))
                info.name = item.get("name", "")
                info.name_cn = item.get("name_cn", "")

                if item.get("rating"):
                    info.bgm_score = item["rating"].get("score")

                if item.get("date"):
                    date_str = item["date"]
                    match = re.search(r"(\d{4})-(\d{2})", date_str)
                    if match:
                        info.year = int(match.group(1))
                        info.month = int(match.group(2))

                if item.get("infobox"):
                    for info_box in item["infobox"]:
                        key = info_box.get("key", "")
                        value = info_box.get("value", "")
                        if key == "动画制作":
                            info.studio = value
                        elif key == "监督":
                            info.director = value
                        elif key == "原作":
                            info.source = value

                info.summary = item.get("summary", "")[:200]
                info.confidence = self._calculate_confidence(keyword, info.name, info.name_cn)
                results.append(info)
        except Exception as e:
            print(f"Bangumi异步搜索错误: {e}")
        return results


class AniListSearcher(BaseSearcher):
    """AniList GraphQL搜索器"""

    GRAPHQL_QUERY = """
    query ($search: String, $type: MediaType, $year: Int, $season: MediaSeason) {
        Page(page: 1, perPage: 20) {
            media(search: $search, type: $type, seasonYear: $year, season: $season) {
                id
                title { romaji, english, native }
                startDate { year, month }
                studios { nodes { name } }
                staff { edges { node { name { full } } role } }
                source
                description
                averageScore
                meanScore
            }
        }
    }
    """

    SOURCE_MAP = {
        "MANGA": "漫画",
        "LIGHT_NOVEL": "轻小说",
        "ORIGINAL": "原创",
        "GAME": "游戏",
        "NOVEL": "小说",
        "VISUAL_NOVEL": "视觉小说",
    }

    SEASON_MAP = {
        (12, 1, 2): "WINTER",
        (3, 4, 5): "SPRING",
        (6, 7, 8): "SUMMER",
        (9, 10, 11): "FALL",
    }

    def __init__(self):
        super().__init__("AniList")
        self.api_url = "https://graphql.anilist.co"
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def search(self, keyword: str, **filters) -> List[AnimeInfo]:
        """搜索AniList"""
        results = []
        try:
            variables = {"search": keyword, "type": "ANIME"}

            # 添加年份过滤
            if filters.get("year"):
                variables["year"] = filters["year"]

            # 添加季度/月份推断
            if filters.get("month"):
                month = filters["month"]
                for months, season in self.SEASON_MAP.items():
                    if month in months:
                        variables["season"] = season
                        break

            response = httpx.post(
                self.api_url,
                headers=self.headers,
                json={"query": self.GRAPHQL_QUERY, "variables": variables},
                timeout=10,
            )
            data = response.json()

            if "data" in data and data["data"]["Page"]["media"]:
                for item in data["data"]["Page"]["media"]:
                    info = AnimeInfo()
                    info.anilist_id = str(item.get("id"))

                    title = item.get("title", {})
                    info.name = title.get("romaji", "")
                    info.name_jp = title.get("native", "")
                    info.name_cn = title.get("english", "")

                    # 日期
                    start_date = item.get("startDate", {})
                    info.year = start_date.get("year")
                    info.month = start_date.get("month")

                    # 制作公司
                    studios = item.get("studios", {}).get("nodes", [])
                    if studios:
                        info.studio = studios[0].get("name", "")

                    # 监督
                    for staff in item.get("staff", {}).get("edges", []):
                        if staff.get("role") == "Director":
                            info.director = staff["node"]["name"]["full"]
                            break

                    # 原作类型
                    info.source = self.SOURCE_MAP.get(
                        item.get("source"), item.get("source", "")
                    )

                    # 评分 (转换为10分制)
                    if item.get("meanScore"):
                        info.anilist_score = item["meanScore"] / 10

                    # 简介，移除HTML标签
                    summary = item.get("description") or ""
                    info.summary = re.sub(r"<[^>]+", "", summary)[:200]

                    # 计算匹配度
                    info.confidence = self._calculate_confidence(
                        keyword, info.name, info.name_cn, info.name_jp
                    )

                    results.append(info)

        except Exception as e:
            print(f"AniList搜索错误: {e}")

        return results

    async def asearch(
        self, client: httpx.AsyncClient, keyword: str, **filters
    ) -> List[AnimeInfo]:
        """异步搜索AniList"""
        results: List[AnimeInfo] = []
        try:
            variables = {"search": keyword, "type": "ANIME"}
            if filters.get("year"):
                variables["year"] = filters["year"]
            if filters.get("month"):
                month = filters["month"]
                for months, season in self.SEASON_MAP.items():
                    if month in months:
                        variables["season"] = season
                        break

            async with _get_search_semaphore():
                response = await client.post(
                    self.api_url,
                    headers=self.headers,
                    json={"query": self.GRAPHQL_QUERY, "variables": variables},
                )
            response.raise_for_status()
            data = response.json()

            for item in data.get("data", {}).get("Page", {}).get("media", []) or []:
                info = AnimeInfo()
                info.anilist_id = str(item.get("id"))

                title = item.get("title", {})
                info.name = title.get("romaji", "")
                info.name_jp = title.get("native", "")
                info.name_cn = title.get("english", "")

                start_date = item.get("startDate", {})
                info.year = start_date.get("year")
                info.month = start_date.get("month")

                studios = item.get("studios", {}).get("nodes", [])
                if studios:
                    info.studio = studios[0].get("name", "")

                for staff in item.get("staff", {}).get("edges", []):
                    if staff.get("role") == "Director":
                        info.director = staff["node"]["name"]["full"]
                        break

                info.source = self.SOURCE_MAP.get(item.get("source"), item.get("source", ""))
                if item.get("meanScore"):
                    info.anilist_score = item["meanScore"] / 10

                summary = item.get("description") or ""
                info.summary = re.sub(r"<[^>]+", "", summary)[:200]
                info.confidence = self._calculate_confidence(
                    keyword, info.name, info.name_cn, info.name_jp
                )
                results.append(info)
        except Exception as e:
            print(f"AniList异步搜索错误: {e}")
        return results


class JikanSearcher(BaseSearcher):
    """Jikan API (MAL非官方API) 搜索器"""

    ALLOWED_TYPES = {"TV", "Movie", "OVA", "ONA"}

    SOURCE_MAP = {
        "Manga": "漫画",
        "Light novel": "轻小说",
        "Original": "原创",
        "Game": "游戏",
        "Novel": "小说",
        "Visual novel": "视觉小说",
    }

    def __init__(self):
        super().__init__("Jikan")
        self.api_base = "https://api.jikan.moe/v4"

    def _search_once(self, keyword: str, **filters) -> List[AnimeInfo]:
        results = []
        params = {
            "q": keyword,
            "sfw": "true",
            "limit": 25,
            "order_by": "popularity",
            "sort": "desc",
        }

        # Jikan的日期过滤比较严格，这里不使用start_date/end_date
        # 改为在获取结果后手动过滤
        year_filter = filters.get("year")

        response = httpx.get(
            f"{self.api_base}/anime", params=params, timeout=15
        )
        data = response.json()

        if "data" in data:
            for item in data["data"]:
                # 仅允许动画剧集/电影/OVA
                anime_type = str(item.get("type") or "").strip()
                if anime_type and anime_type not in self.ALLOWED_TYPES:
                    continue

                # 如果有年份过滤，跳过不匹配的结果
                if year_filter and item.get("aired"):
                    from_date = item["aired"].get("from", "")
                    if from_date:
                        match = re.search(r"(\d{4})", from_date)
                        if match:
                            item_year = int(match.group(1))
                            # 允许前后一年的误差
                            if abs(item_year - year_filter) > 1:
                                continue

                info = AnimeInfo()
                info.mal_id = str(item.get("mal_id"))
                info.name = item.get("titles", [{}])[0].get("title", "")

                # 获取所有标题
                for title_obj in item.get("titles", []):
                    title_type = title_obj.get("type", "")
                    title_text = title_obj.get("title", "")
                    if title_type == "Japanese":
                        info.name_jp = title_text
                    elif title_type == "English":
                        info.name_cn = title_text

                # 日期
                if item.get("aired"):
                    from_date = item["aired"].get("from", "")
                    if from_date:
                        match = re.search(r"(\d{4})-(\d{2})", from_date)
                        if match:
                            info.year = int(match.group(1))
                            info.month = int(match.group(2))

                # 制作公司
                studios = item.get("studios", [])
                if studios:
                    info.studio = studios[0].get("name", "")

                # 原作类型
                info.source = self.SOURCE_MAP.get(
                    item.get("source"), item.get("source", "")
                )

                # 评分
                info.mal_score = item.get("score")

                # 简介
                summary = item.get("synopsis") or ""
                info.summary = summary[:200]

                # 计算匹配度
                info.confidence = self._calculate_confidence(
                    keyword, info.name, info.name_cn, info.name_jp
                )

                results.append(info)

        return results

    def search(self, keyword: str, **filters) -> List[AnimeInfo]:
        """搜索MyAnimeList"""
        results = []
        try:
            results = self._search_once(keyword, **filters)

        except Exception as e:
            print(f"Jikan搜索错误: {e}")

        return results

    async def _asearch_once(
        self, client: httpx.AsyncClient, keyword: str, **filters
    ) -> List[AnimeInfo]:
        results: List[AnimeInfo] = []
        params = {
            "q": keyword,
            "sfw": "true",
            "limit": 25,
            "order_by": "popularity",
            "sort": "desc",
        }
        year_filter = filters.get("year")

        async with _get_search_semaphore():
            response = await client.get(f"{self.api_base}/anime", params=params)
        response.raise_for_status()
        data = response.json()

        for item in data.get("data", []):
            anime_type = str(item.get("type") or "").strip()
            if anime_type and anime_type not in self.ALLOWED_TYPES:
                continue

            if year_filter and item.get("aired"):
                from_date = item["aired"].get("from", "")
                if from_date:
                    match = re.search(r"(\d{4})", from_date)
                    if match:
                        item_year = int(match.group(1))
                        if abs(item_year - year_filter) > 1:
                            continue

            info = AnimeInfo()
            info.mal_id = str(item.get("mal_id"))
            info.name = item.get("titles", [{}])[0].get("title", "")

            for title_obj in item.get("titles", []):
                title_type = title_obj.get("type", "")
                title_text = title_obj.get("title", "")
                if title_type == "Japanese":
                    info.name_jp = title_text
                elif title_type == "English":
                    info.name_cn = title_text

            if item.get("aired"):
                from_date = item["aired"].get("from", "")
                if from_date:
                    match = re.search(r"(\d{4})-(\d{2})", from_date)
                    if match:
                        info.year = int(match.group(1))
                        info.month = int(match.group(2))

            studios = item.get("studios", [])
            if studios:
                info.studio = studios[0].get("name", "")

            info.source = self.SOURCE_MAP.get(item.get("source"), item.get("source", ""))
            info.mal_score = item.get("score")
            info.summary = (item.get("synopsis") or "")[:200]
            info.confidence = self._calculate_confidence(
                keyword, info.name, info.name_cn, info.name_jp
            )
            results.append(info)
        return results

    async def asearch(
        self, client: httpx.AsyncClient, keyword: str, **filters
    ) -> List[AnimeInfo]:
        """异步搜索Jikan"""
        try:
            return await self._asearch_once(client, keyword, **filters)
        except Exception as e:
            print(f"Jikan异步搜索错误: {e}")
            return []


class CrossValidator:
    """交叉验证器 - 整合多源搜索结果"""

    # 同一动画的不同语言标题映射（已知的常见差异）
    TITLE_PATTERNS = {
        "frieren": ["葬送", "frieren", "sousou"],
        "shingeki": ["进击", "巨人", "shingeki", "kyojin", "attack on titan"],
        "kimetsu": ["鬼灭", "kimetsu", "yaiba"],
        "jujutsu": ["咒术", "jujutsu", "kaisen"],
        "spy_family": ["间谍", "spy", "family"],
        "chainsaw": ["电锯", "chainsaw", "man"],
        "bleach": ["死神", "bleach"],
        "naruto": ["火影", "naruto"],
        "onepiece": ["海贼", "one piece"],
    }

    def __init__(self, match_mode: str = "normal"):
        self.bgm = BangumiSearcher()
        self.anilist = AniListSearcher()
        self.jikan = JikanSearcher()
        self.match_mode = match_mode

    @staticmethod
    def _build_extra_name_queries(keyword: str, *result_lists: List[AnimeInfo]) -> List[str]:
        candidates = [keyword]
        for infos in result_lists:
            for info in infos:
                for title in [info.name, info.name_cn, info.name_jp]:
                    if title and len(_normalize_title(title)) >= 2:
                        candidates.append(title)

        seen = set()
        uniq = []
        for c in candidates:
            norm = _normalize_title(c)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            uniq.append(c)
        return uniq[:6]

    def search(self, keyword: str, **filters) -> List[AnimeInfo]:
        """
        多源交叉验证搜索

        Args:
            keyword: 搜索关键词
            filters: 过滤条件 {year, month, studio, director}

        Returns:
            经过交叉验证排序的AnimeInfo列表
        """
        all_results = []

        # 并发搜索所有源
        bgm_results = self.bgm.search(keyword, **filters)
        all_results.extend(bgm_results)

        anilist_results = self.anilist.search(keyword, **filters)
        all_results.extend(anilist_results)

        # Use title candidates from early sources to improve cross-platform recall.
        extra_queries = self._build_extra_name_queries(keyword, bgm_results, anilist_results)

        # Extra AniList search using candidate names when available.
        for q in extra_queries[1:4]:
            try:
                extra = self.anilist.search(q, **filters)
                all_results.extend(extra)
            except Exception:
                pass

        # Extra Jikan search using candidate names (important when no id mapping exists).
        for q in extra_queries[1:6]:
            try:
                extra = self.jikan.search(q, **filters)
                all_results.extend(extra)
            except Exception:
                pass
        jikan_results = self.jikan.search(keyword, **filters)
        all_results.extend(jikan_results)

        # Enrich IDs using BangumiExtLinker mapping
        if lookup_ext_ids:
            for info in all_results:
                ext = lookup_ext_ids(bgm_id=info.bgm_id, mal_id=info.mal_id)
                if not ext:
                    continue
                if not info.bgm_id and ext.get("bgm_id"):
                    info.bgm_id = str(ext.get("bgm_id"))
                if not info.mal_id and ext.get("mal_id"):
                    info.mal_id = str(ext.get("mal_id"))

        # 合并和交叉验证
        validated = self._cross_validate(all_results, filters)
        # Fallback: when mapping is missing, recover MAL IDs by title matching.
        self._enrich_missing_mal(validated, filters)

        # 按置信度排序
        validated.sort(key=lambda x: x.confidence, reverse=True)

        return validated

    async def asearch(self, keyword: str, **filters) -> List[AnimeInfo]:
        """异步多源交叉验证搜索"""
        all_results: List[AnimeInfo] = []

        async with _build_async_client() as client:
            bgm_task = self.bgm.asearch(client, keyword, **filters)
            anl_task = self.anilist.asearch(client, keyword, **filters)
            bgm_results, anilist_results = await asyncio.gather(
                bgm_task, anl_task, return_exceptions=True
            )

            if isinstance(bgm_results, Exception):
                bgm_results = []
            if isinstance(anilist_results, Exception):
                anilist_results = []

            all_results.extend(bgm_results)
            all_results.extend(anilist_results)

            extra_queries = self._build_extra_name_queries(keyword, bgm_results, anilist_results)

            anl_extra_tasks = [
                self.anilist.asearch(client, q, **filters) for q in extra_queries[1:4]
            ]
            if anl_extra_tasks:
                anl_extra = await asyncio.gather(*anl_extra_tasks, return_exceptions=True)
                for one in anl_extra:
                    if isinstance(one, list):
                        all_results.extend(one)

            jikan_tasks = [
                self.jikan.asearch(client, q, **filters) for q in extra_queries[1:6]
            ]
            jikan_tasks.append(self.jikan.asearch(client, keyword, **filters))
            jikan_extra = await asyncio.gather(*jikan_tasks, return_exceptions=True)
            for one in jikan_extra:
                if isinstance(one, list):
                    all_results.extend(one)

        if lookup_ext_ids:
            for info in all_results:
                ext = lookup_ext_ids(bgm_id=info.bgm_id, mal_id=info.mal_id)
                if not ext:
                    continue
                if not info.bgm_id and ext.get("bgm_id"):
                    info.bgm_id = str(ext.get("bgm_id"))
                if not info.mal_id and ext.get("mal_id"):
                    info.mal_id = str(ext.get("mal_id"))

        validated = self._cross_validate(all_results, filters)
        self._enrich_missing_mal(validated, filters)
        validated.sort(key=lambda x: x.confidence, reverse=True)
        return validated

    @staticmethod
    def _best_title_similarity(target: AnimeInfo, cand: AnimeInfo) -> float:
        t_names = [n for n in target.get_all_names() if n]
        c_names = [n for n in cand.get_all_names() if n]
        if not t_names or not c_names:
            return 0.0
        best = 0.0
        for a in t_names:
            for b in c_names:
                best = max(best, _similarity_score(a, b))
        return best

    def _enrich_missing_mal(self, results: List[AnimeInfo], filters: Dict) -> None:
        if not results:
            return

        cache: Dict[str, List[AnimeInfo]] = {}
        for item in results:
            if item.mal_id:
                continue

            queries = []
            for t in [item.name_jp, item.name, item.name_cn]:
                if t:
                    queries.append(t)

            # unique + normalized
            seen = set()
            uniq_queries = []
            for q in queries:
                nq = _normalize_title(q)
                if not nq or nq in seen:
                    continue
                seen.add(nq)
                uniq_queries.append(q)

            # OVA/Movie can be far from base year; don't hard-limit by year here.
            relaxed_filters = {k: v for k, v in filters.items() if k != "year"}

            picked = None
            for q in uniq_queries[:3]:
                if q not in cache:
                    try:
                        cache[q] = self.jikan.search(q, **relaxed_filters)
                    except Exception:
                        cache[q] = []

                # 规范：优先使用 MAL 搜索结果第一条（在基础匹配通过时）
                for idx, cand in enumerate(cache[q]):
                    score = self._best_title_similarity(item, cand)
                    if idx == 0 and score >= 0.60:
                        picked = (cand, score)
                        break
                    if score >= 0.72:
                        picked = (cand, score)
                        break
                if picked:
                    break

            if picked:
                best_match, best_score = picked
                item.mal_id = best_match.mal_id
                if item.mal_score is None:
                    item.mal_score = best_match.mal_score
                if not item.name_jp and best_match.name_jp:
                    item.name_jp = best_match.name_jp
                if not item.name_cn and best_match.name_cn:
                    item.name_cn = best_match.name_cn
                item.confidence = min(1.0, max(item.confidence, best_score))

    def _cross_validate(
        self, results: List[AnimeInfo], filters: Dict
    ) -> List[AnimeInfo]:
        """交叉验证并合并结果"""
        if not results:
            return []

        # 按名称相似度分组
        groups: List[List[AnimeInfo]] = []
        used = set()

        for i, info in enumerate(results):
            if i in used:
                continue

            # 创建新组
            group = [info]
            used.add(i)

            # 查找相似的
            for j, other in enumerate(results[i + 1 :], i + 1):
                if j in used:
                    continue
                if self._is_same_anime(info, other):
                    group.append(other)
                    used.add(j)

            groups.append(group)

        # 合并每组
        merged = [self._merge_group(group) for group in groups]

        # 应用额外过滤
        return self._apply_filters(merged, filters)

    def _is_same_anime(self, a: AnimeInfo, b: AnimeInfo) -> bool:
        """判断两个AnimeInfo是否代表同一部动画"""
        # 1. 如果ID相同，肯定是同一部
        if a.bgm_id and b.bgm_id and a.bgm_id == b.bgm_id:
            return True
        if a.mal_id and b.mal_id and a.mal_id == b.mal_id:
            return True
        if a.anilist_id and b.anilist_id and a.anilist_id == b.anilist_id:
            return True

        # 2. 检查年份是否相近（如果都有年份）
        if a.year and b.year:
            if abs(a.year - b.year) > 1:
                return False

        # 3. 检查标题相似度
        a_names = a.get_all_names()
        b_names = b.get_all_names()
        year_delta = None
        if a.year and b.year:
            year_delta = abs(a.year - b.year)

        # 标准化后比较
        for a_name in a_names:
            for b_name in b_names:
                if self._titles_match(
                    a_name, b_name, year_delta=year_delta, mode=self.match_mode
                ):
                    return True

        # 4. 检查关键词匹配
        for pattern_keywords in self.TITLE_PATTERNS.values():
            a_matches = sum(
                1
                for k in pattern_keywords
                if any(k in _normalize_title(n) for n in a_names)
            )
            b_matches = sum(
                1
                for k in pattern_keywords
                if any(k in _normalize_title(n) for n in b_names)
            )
            if a_matches >= 2 and b_matches >= 2:
                return True
            if any(len(k) >= 4 for k in pattern_keywords) and a_matches > 0 and b_matches > 0:
                return True

        return False

    def _titles_match(
        self,
        title1: str,
        title2: str,
        year_delta: Optional[int] = None,
        mode: str = "normal",
    ) -> bool:
        if not title1 or not title2:
            return False

        n1 = _normalize_title(title1)
        n2 = _normalize_title(title2)
        if not n1 or not n2:
            return False
        if n1 == n2:
            return True

        score = _similarity_score(title1, title2, mode=mode)
        both_jp = _has_japanese(title1) and _has_japanese(title2)
        threshold = 0.80 if both_jp else 0.86
        if year_delta == 0:
            threshold -= 0.03
        elif year_delta == 1:
            threshold -= 0.01
        if mode == "strict":
            threshold += 0.03
        elif mode == "recall":
            threshold -= 0.03
        min_len = min(len(n1), len(n2))
        if min_len <= 4:
            threshold += 0.06
        if score >= threshold:
            return True

        token_overlap = _token_overlap_score(title1, title2)
        if token_overlap >= 0.85:
            return True

        if len(n1) > 6 and len(n2) > 6:
            if n1 in n2 or n2 in n1:
                return True
            if _contains_all_tokens(n1, n2) or _contains_all_tokens(n2, n1):
                return True

        return False


    def _merge_group(self, group: List[AnimeInfo]) -> AnimeInfo:
        """合并同一组的结果"""
        if len(group) == 1:
            return group[0]

        # 选择信息最完整的作为基础
        base = max(
            group,
            key=lambda x: (
                sum([bool(x.bgm_id), bool(x.mal_id), bool(x.anilist_id)]),
                sum([bool(x.name), bool(x.name_cn), bool(x.name_jp)]),
                x.confidence,
            ),
        )
        merged = AnimeInfo(
            bgm_id=base.bgm_id,
            mal_id=base.mal_id,
            anilist_id=base.anilist_id,
            name=base.name,
            name_cn=base.name_cn or "",
            name_jp=base.name_jp or "",
            year=base.year,
            month=base.month,
            studio=base.studio or "",
            director=base.director or "",
            source=base.source or "",
            bgm_score=base.bgm_score,
            mal_score=base.mal_score,
            anilist_score=base.anilist_score,
            summary=base.summary or "",
            confidence=base.confidence,
        )

        # 合并其他信息
        source_count = 1
        for other in group:
            if other is base:
                continue

            # 补充ID
            if other.bgm_id and not merged.bgm_id:
                merged.bgm_id = other.bgm_id
            if other.mal_id and not merged.mal_id:
                merged.mal_id = other.mal_id
            if other.anilist_id and not merged.anilist_id:
                merged.anilist_id = other.anilist_id

            # 合并评分
            if other.bgm_score and not merged.bgm_score:
                merged.bgm_score = other.bgm_score
            if other.mal_score and not merged.mal_score:
                merged.mal_score = other.mal_score
            if other.anilist_score and not merged.anilist_score:
                merged.anilist_score = other.anilist_score

            # 合并其他信息
            if not merged.name_cn and other.name_cn:
                merged.name_cn = other.name_cn
            if not merged.name_jp and other.name_jp:
                merged.name_jp = other.name_jp
            if not merged.studio and other.studio:
                merged.studio = other.studio
            if not merged.director and other.director:
                merged.director = other.director
            if not merged.source and other.source:
                merged.source = other.source
            if not merged.summary and other.summary:
                merged.summary = other.summary

            # 提升置信度
            source_count += 1

        # 多源匹配提升置信度
        max_conf = max([g.confidence for g in group] + [merged.confidence])
        merged.confidence = min(1.0, max_conf + 0.12 * (source_count - 1))

        return merged

    def _apply_filters(
        self, results: List[AnimeInfo], filters: Dict
    ) -> List[AnimeInfo]:
        """应用过滤条件"""
        filtered = results

        if filters.get("studio"):
            studio_filter = filters["studio"].lower()
            filtered = [r for r in filtered if studio_filter in r.studio.lower()]

        if filters.get("director"):
            director_filter = filters["director"].lower()
            filtered = [r for r in filtered if director_filter in r.director.lower()]

        if filters.get("source"):
            source_filter = filters["source"]
            filtered = [r for r in filtered if source_filter in r.source]

        # 软性提升：与过滤条件越接近，置信度越高
        year_filter = filters.get("year")
        month_filter = filters.get("month")
        studio_filter = (filters.get("studio") or "").lower()
        director_filter = (filters.get("director") or "").lower()
        source_filter = filters.get("source") or ""

        for r in filtered:
            boost = 0.0
            if year_filter and r.year:
                delta = abs(r.year - year_filter)
                if delta == 0:
                    boost += 0.06
                elif delta == 1:
                    boost += 0.03
                else:
                    boost -= 0.03
            if month_filter and r.month:
                boost += 0.03 if r.month == month_filter else -0.01
            if studio_filter and r.studio and studio_filter in r.studio.lower():
                boost += 0.05
            if director_filter and r.director and director_filter in r.director.lower():
                boost += 0.05
            if source_filter and r.source and source_filter in r.source:
                boost += 0.03
            if boost != 0.0:
                r.confidence = max(0.0, min(1.0, r.confidence + boost))

        return filtered

    @staticmethod
    def _normalize_name(name: str) -> str:
        """标准化名称用于比较"""
        # 转小写，移除特殊字符和空格
        normalized = re.sub(r"[^\w]", "", name.lower()).strip()
        # 移除常见的停用词
        for word in ["the", "a", "an", "no", "na"]:
            normalized = normalized.replace(word, "")
        return normalized


async def search_anime_precise_async(
    keyword: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    studio: Optional[str] = None,
    director: Optional[str] = None,
    source: Optional[str] = None,
    include_extra_scores: bool = False,
    debug_scores: bool = False,
    match_mode: str = "normal",
    top_n: int = 10,
) -> List[dict]:
    """
    异步便捷函数：执行精确搜索并返回字典列表。
    """
    filters = {
        "year": year,
        "month": month,
        "studio": studio,
        "director": director,
        "source": source,
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    validator = CrossValidator(match_mode=match_mode)
    results = await validator.asearch(keyword, **filters)

    output = []
    for r in results[:top_n]:
        item = r.to_dict()
        if lookup_ext_ids:
            ext = lookup_ext_ids(bgm_id=item.get("bgm_id"), mal_id=item.get("mal_id"))
            if ext:
                if not item.get("bgm_id") and ext.get("bgm_id"):
                    item["bgm_id"] = str(ext.get("bgm_id"))
                if not item.get("mal_id") and ext.get("mal_id"):
                    item["mal_id"] = str(ext.get("mal_id"))
                for key in [
                    "douban_id",
                    "bili_id",
                    "anidb_id",
                    "tmdb_id",
                    "imdb_id",
                    "tvdb_id",
                    "wikidata_id",
                ]:
                    if ext.get(key) and not item.get(key):
                        item[key] = ext.get(key)

        if include_extra_scores:
            debug_payload = None
            if debug_scores:
                extra, debug_payload = await asyncio.to_thread(
                    _fetch_extra_scores_debug,
                    item.get("name", ""),
                    item.get("name_cn", ""),
                    item.get("name_jp", ""),
                )
            else:
                extra = await asyncio.to_thread(
                    _fetch_extra_scores,
                    item.get("name", ""),
                    item.get("name_cn", ""),
                    item.get("name_jp", ""),
                )
            if extra:
                item.update(extra)
            _merge_local_extra_scores(item, debug=debug_payload)
            if debug_scores:
                item["debug_scores"] = debug_payload or {}

        output.append(item)

    return output


def search_anime_precise(
    keyword: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    studio: Optional[str] = None,
    director: Optional[str] = None,
    source: Optional[str] = None,
    include_extra_scores: bool = False,
    debug_scores: bool = False,
    match_mode: str = "normal",
    top_n: int = 10,
) -> List[dict]:
    """
    便捷函数：执行精确搜索并返回字典列表

    Args:
        keyword: 搜索关键词
        year: 年份过滤
        month: 月份过滤
        studio: 制作公司过滤
        director: 监督过滤
        source: 原作类型过滤
        top_n: 返回结果数量限制

    Returns:
        搜索结果字典列表
    """
    filters = {
        "year": year,
        "month": month,
        "studio": studio,
        "director": director,
        "source": source,
    }
    # 移除None值
    filters = {k: v for k, v in filters.items() if v is not None}

    validator = CrossValidator(match_mode=match_mode)
    results = validator.search(keyword, **filters)

    output = []
    for r in results[:top_n]:
        item = r.to_dict()
        if lookup_ext_ids:
            ext = lookup_ext_ids(bgm_id=item.get("bgm_id"), mal_id=item.get("mal_id"))
            if ext:
                # Fill missing core IDs
                if not item.get("bgm_id") and ext.get("bgm_id"):
                    item["bgm_id"] = str(ext.get("bgm_id"))
                if not item.get("mal_id") and ext.get("mal_id"):
                    item["mal_id"] = str(ext.get("mal_id"))

                # Attach extra IDs if present
                for key in [
                    "douban_id",
                    "bili_id",
                    "anidb_id",
                    "tmdb_id",
                    "imdb_id",
                    "tvdb_id",
                    "wikidata_id",
                ]:
                    if ext.get(key) and not item.get(key):
                        item[key] = ext.get(key)

        if include_extra_scores:
            debug_payload = None
            if debug_scores:
                extra, debug_payload = _fetch_extra_scores_debug(
                    item.get("name", ""),
                    item.get("name_cn", ""),
                    item.get("name_jp", ""),
                )
            else:
                extra = _fetch_extra_scores(
                    item.get("name", ""),
                    item.get("name_cn", ""),
                    item.get("name_jp", ""),
                )
            if extra:
                item.update(extra)
            # Fallback to local scored datasets when online scraping misses.
            _merge_local_extra_scores(item, debug=debug_payload)
            if debug_scores:
                item["debug_scores"] = debug_payload or {}

        output.append(item)

    return output
