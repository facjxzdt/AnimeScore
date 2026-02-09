#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多源交叉验证的精确动画搜索
支持Bangumi、AniList、MAL(Jikan API)多源搜索并交叉验证
"""

import re
import unicodedata
from functools import lru_cache
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

import requests

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
    from utils.ext_linker import lookup_ext_ids
except Exception:
    lookup_ext_ids = None


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
    t = re.sub(r"\[.*?\]|\(.*?\)|\{.*?\}|<.*?>", " ", t)
    t = re.sub(r"(season|part|cour)\s*\d+", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(s\d+|s\d+\s*e\d+|ova|oad|sp|special|movie|tv)\b", " ", t)
    t = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t




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


def _similarity_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    jac = _ngram_jaccard(na, nb, n=2)
    rf = 0.0
    if rapidfuzz_fuzz:
        try:
            rf = rapidfuzz_fuzz.token_set_ratio(na, nb) / 100.0
        except Exception:
            rf = 0.0
    scores = [seq, jac, rf]
    scores.sort()
    base_score = scores[2] * 0.7 + scores[1] * 0.3

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

            response = requests.post(
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

            response = requests.post(
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


class JikanSearcher(BaseSearcher):
    """Jikan API (MAL非官方API) 搜索器"""

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

    def search(self, keyword: str, **filters) -> List[AnimeInfo]:
        """搜索MyAnimeList"""
        results = []
        try:
            params = {
                "q": keyword,
                "type": "tv",
                "sfw": "true",
                "limit": 20,
                "order_by": "popularity",
                "sort": "asc",
            }

            # Jikan的日期过滤比较严格，这里不使用start_date/end_date
            # 改为在获取结果后手动过滤
            year_filter = filters.get("year")

            response = requests.get(
                f"{self.api_base}/anime", params=params, timeout=15
            )
            data = response.json()

            if "data" in data:
                for item in data["data"]:
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

        except Exception as e:
            print(f"Jikan搜索错误: {e}")

        return results


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

    def __init__(self):
        self.bgm = BangumiSearcher()
        self.anilist = AniListSearcher()
        self.jikan = JikanSearcher()

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

        # Extra AniList search using Japanese titles when available
        if not _has_japanese(keyword) and bgm_results:
            jp_candidates = []
            for info in bgm_results:
                if info.name and _has_japanese(info.name):
                    jp_candidates.append(info.name)
            # keep unique order, cap to 3 queries for latency
            seen = set()
            uniq = []
            for t in jp_candidates:
                if t not in seen:
                    seen.add(t)
                    uniq.append(t)
            for jp_title in uniq[:3]:
                try:
                    extra = self.anilist.search(jp_title, **filters)
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

        # 按置信度排序
        validated.sort(key=lambda x: x.confidence, reverse=True)

        return validated

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

        # 标准化后比较
        for a_name in a_names:
            for b_name in b_names:
                if self._titles_match(a_name, b_name):
                    return True

        # 4. 检查关键词匹配
        for pattern_keywords in self.TITLE_PATTERNS.values():
            a_matches = sum(1 for k in pattern_keywords if any(k in n.lower() for n in a_names))
            b_matches = sum(1 for k in pattern_keywords if any(k in n.lower() for n in b_names))
            if a_matches > 0 and b_matches > 0:
                return True

        return False

    def _titles_match(self, title1: str, title2: str) -> bool:
        if not title1 or not title2:
            return False

        score = _similarity_score(title1, title2)
        both_jp = _has_japanese(title1) and _has_japanese(title2)
        threshold = 0.78 if both_jp else 0.85
        if score >= threshold:
            return True

        n1 = _normalize_title(title1)
        n2 = _normalize_title(title2)
        if len(n1) > 6 and len(n2) > 6:
            if n1 in n2 or n2 in n1:
                return True

        return False


    def _merge_group(self, group: List[AnimeInfo]) -> AnimeInfo:
        """合并同一组的结果"""
        if len(group) == 1:
            return group[0]

        # 选择信息最完整的作为基础
        base = max(group, key=lambda x: sum([bool(x.bgm_id), bool(x.mal_id), bool(x.anilist_id)]))
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
        merged.confidence = min(1.0, merged.confidence + 0.15 * (source_count - 1))

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


def search_anime_precise(
    keyword: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    studio: Optional[str] = None,
    director: Optional[str] = None,
    source: Optional[str] = None,
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

    validator = CrossValidator()
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

        output.append(item)

    return output
