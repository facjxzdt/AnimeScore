"""Evidence-based Filmarks discovery: seasonal index, aliases and related seasons."""

import asyncio
import json
import re
import time
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from services.analytics import AnalyticsStore
from services.catalog import normalize_title
from services.mappings import MappingConflict, MappingStore, identity
from services.http import retry_deadline
from services.providers import normalize_id, site_url
from services.ratings import merge_ratings
from services.scrapers import parse_rating

ALGORITHM_VERSION = 3


def title_key(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"^(?:tvアニメ|アニメ)\s*[「『]", "", value)
    numbers = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    def ordinal(match):
        numeral = match[1]
        if "十" in numeral:
            tens, units = numeral.split("十")
            number = numbers.get(tens, 1) * 10 + numbers.get(units, 0)
        else:
            number = numbers.get(numeral, numeral)
        return f"第{number}{match[2]}"
    value = re.sub(r"第?([一二三四五六七八九]?十[一二三四五六七八九]?|[一二三四五六七八九])(期|クール)", ordinal, value)
    value = re.sub(r"(?:season\s*(\d+)|(\d+)(?:st|nd|rd|th)\s*season|第?(\d+)期|シーズン\s*(\d+))",
                   lambda m: "season" + next(v for v in m.groups() if v), value)
    romans = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9"}
    value = re.sub(r"(?<![a-z])(?:viii|vii|iii|ii|iv|vi|ix|v)(?![a-z])", lambda m: "season" + romans[m[0]], value)
    value = value.replace("season season", "season")
    # A first cour label is optional; later cours remain part of the identity.
    value = re.sub(r"第1クール|season1\b", "", value)
    return normalize_title(value)


def aliases(item):
    values = [item["name"], *(name for names in item.get("titles", {}).values() for name in names)]
    return list(dict.fromkeys(value for value in values if value))


def release_date(value):
    if not value:
        return None
    match = re.search(r"(\d{4})[年-](\d{1,2})[月-](\d{1,2})", str(value))
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return None


def work_id(url):
    try:
        return normalize_id("filmarks", "https://filmarks.com" + url if url.startswith("/") else url)
    except ValueError:
        return None


def parse_listing(html):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".p-content-cassette")
    if not cards and not soup.select_one("h1.c-heading-1"):
        raise ValueError("Filmarks 目录结构异常或访问受限")
    items = {}
    for card in cards:
        title = card.select_one(".p-content-cassette__title")
        identifier = next((work_id(a["href"]) for a in card.select("a[href]") if work_id(a["href"])), None)
        if not identifier:
            # Cards without reviews may navigate through Vue instead of an anchor.
            handler = card.get("@click", card.get("v-on:click", ""))
            link = re.search(r"onClickDetailLink\(\s*\$event\s*,\s*(['\"])(/animes/[1-9]\d*/[1-9]\d*)\1\s*\)", handler)
            identifier = work_id(link[2]) if link else None
        info = card.select_one(".p-content-cassette__other-info")
        if title and identifier:
            items[identifier] = {"id": identifier, "title": title.get_text(" ", strip=True),
                                 "date": release_date(info.get_text(" ", strip=True) if info else None), "verified": False}
    return {"items": list(items.values()), "has_next": soup.select_one('a[rel~="next"]') is not None}


def parse_work(html, identifier):
    soup = BeautifulSoup(html, "html.parser")
    canonical = soup.select_one('link[rel="canonical"]')
    if not canonical or work_id(canonical.get("href", "")) != identifier:
        raise ValueError("Filmarks 作品 ID 核对失败")
    work = None
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.get_text())
            entries = value if isinstance(value, list) else value.get("@graph", [value])
            work = next((entry for entry in entries if isinstance(entry, dict) and entry.get("@type") == "TVSeason"), work)
        except (ValueError, AttributeError):
            continue
    title = (work or {}).get("title") or (work or {}).get("name")
    if not title:
        node = soup.select_one(".p-content-detail__title > span")
        title = node.get_text(strip=True) if node else None
    if not title:
        raise ValueError("Filmarks 作品名称缺失")
    official = next((a.get("href") for a in soup.select("a[href]") if a.get_text(strip=True) == "公式サイト"), None)
    related = {}
    for a in soup.select("a[href]"):
        key = work_id(a["href"])
        label = a.get_text(" ", strip=True)
        if key and key != identifier and key.split("/")[0] == identifier.split("/")[0] and label and not re.fullmatch(r"シーズン\d+", label):
            related[key] = {"id": key, "title": label, "date": None, "verified": False}
    return {"id": identifier, "title": title,
            "date": release_date((work or {}).get("releaseDate") or (work or {}).get("startDate")),
            "official_site": official, "verified": True, "related": list(related.values()),
            "rating": parse_rating("filmarks", html)}


def evaluate(item, candidate):
    keys = [title_key(name) for name in aliases(item)]
    key = title_key(candidate["title"])
    base = lambda value: re.sub(r"season\d+|第\d+クール", "", value)
    # Shared season labels alone must not promote unrelated series as candidates.
    similarity = max((min(SequenceMatcher(None, key, value).ratio(),
                          SequenceMatcher(None, base(key), base(value)).ratio()) for value in keys), default=0)
    exact = key in keys
    target_date, found_date = release_date(item.get("begin")), candidate.get("date")
    gap = abs((date.fromisoformat(target_date) - date.fromisoformat(found_date)).days) if target_date and found_date else None
    date_match = gap is not None and gap <= 31
    reasons = ["名称一致" if exact else f"名称相似度 {similarity:.0%}"]
    if gap is not None:
        reasons.append(f"开播日期相差 {gap} 天")
    else:
        reasons.append("缺少开播日期")
    if not candidate.get("verified"):
        reasons.append("作品页未验证")
    return {**{k: v for k, v in candidate.items() if k not in {"rating", "related"}},
            "url": site_url("filmarks", candidate["id"]), "similarity": round(similarity, 4),
            "score": round(similarity * 80 + (20 if date_match else 0), 2), "reasons": reasons,
            "eligible": bool(exact and date_match and candidate.get("verified") and item.get("type") != "movie")}


class FilmarksMapper:
    def __init__(self, repository, ratings):
        self.repository, self.ratings, self.cache = repository, ratings, ratings.cache
        self.store = MappingStore(self.cache)
        self.lock = asyncio.Lock()
        with self.cache.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS filmarks_pages (key TEXT PRIMARY KEY, updated_at REAL, payload TEXT);
                CREATE TABLE IF NOT EXISTS filmarks_matches (entity TEXT PRIMARY KEY, catalog_id TEXT, updated_at REAL, payload TEXT);
            """)

    def result(self, item):
        with self.cache.connect() as db:
            row = db.execute("SELECT payload FROM filmarks_matches WHERE entity=?", (identity(item),)).fetchone()
        return json.loads(row[0]) if row else {"status": "unchecked", "candidates": [], "errors": []}

    def results(self):
        with self.cache.connect() as db:
            return {row[0]: json.loads(row[1]) for row in db.execute("SELECT catalog_id, payload FROM filmarks_matches")}

    def _save(self, item, result):
        result = {**result, "catalog_id": item["catalog_id"], "checked_at": time.time(), "algorithm": ALGORITHM_VERSION}
        with self.cache.connect() as db:
            db.execute("INSERT OR REPLACE INTO filmarks_matches VALUES (?, ?, ?, ?)",
                       (identity(item), item["catalog_id"], result["checked_at"], json.dumps(result)))
        return result

    async def _page(self, path, params=None, identifier=None):
        url = "https://filmarks.com" + path + ("?" + urlencode(params) if params else "")
        cache_key = url if identifier else "listing-v2:" + url
        with self.cache.connect() as db:
            row = db.execute("SELECT updated_at, payload FROM filmarks_pages WHERE key=?", (cache_key,)).fetchone()
        if row and time.time() - row[0] < 86400:
            return json.loads(row[1])
        async with self.ratings.locks["filmarks"]:
            if self.ratings.blocked_until["filmarks"] > time.time():
                raise ValueError("Filmarks 正在限流冷却")
            delay = self.ratings.intervals["filmarks"] - (time.monotonic() - self.ratings.last_request["filmarks"])
            if delay > 0:
                await asyncio.sleep(delay)
            self.ratings.last_request["filmarks"] = time.monotonic()
            response = await self.ratings.client.get(url, timeout=15, follow_redirects=False)
            if response.status_code in {403, 429}:
                self.ratings.blocked_until["filmarks"] = retry_deadline(response.headers.get("Retry-After", "300"), minimum=300)
            missing_season = (not identifier and response.status_code in {404, 410}
                              and re.fullmatch(r"/list-anime/release_year/\d{4}/(?:1|4|7|10)", path))
            if missing_season:
                # Optional seasonal indexes may not exist; cache the miss and search by title.
                data = {"items": [], "has_next": False}
            else:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError(f"Filmarks HTTP {response.status_code}")
                data = await asyncio.to_thread(parse_work, response.text, identifier) if identifier else await asyncio.to_thread(parse_listing, response.text)
            now = time.time()
            with self.cache.connect() as db:
                db.execute("INSERT OR REPLACE INTO filmarks_pages VALUES (?, ?, ?)", (cache_key, now, json.dumps(data)))
            if identifier:
                rating = data["rating"]
                self.cache.write("filmarks", identifier, {**rating, "status": "ok" if rating["score"] is not None else "no_score",
                                                         "updated_at": now, "retry_at": now + self.ratings.ttl})
            return data

    async def _listing(self, path, params=None, pages=8):
        items = {}
        for page in range(1, pages + 1):
            data = await self._page(path, {**(params or {}), **({"page": page} if page > 1 else {})})
            items.update({item["id"]: item for item in data["items"]})
            if not data["has_next"]:
                return list(items.values()), False
        return list(items.values()), True

    async def discover(self, item, *, apply=False, force=False):
        async with self.lock:
            detail = await asyncio.to_thread(self.store.detail, item)
            if apply and (detail["item"]["ids"].get("filmarks_id") or "filmarks" in detail["overrides"]):
                return {**self.result(item), "status": "skipped", "reason": "已有映射或人工禁用"}
            previous = self.result(item)
            if not force and previous.get("algorithm") == ALGORITHM_VERSION and time.time() - previous.get("checked_at", 0) < (3600 if previous.get("status") == "error" else 86400):
                if apply and previous.get("status") == "matched":
                    return await self._apply(item, detail, previous)
                return previous
            pool, errors, methods = {}, [], []
            async def add_listing(path, params=None, label="季度目录", pages=8):
                try:
                    values, truncated = await self._listing(path, params, pages)
                    for value in values:
                        pool.setdefault(value["id"], {**value, "method": label})
                    methods.append(label)
                    if truncated:
                        errors.append(label + "仅检查前 " + str(pages) + " 页")
                except Exception as exc:
                    errors.append(label + ": " + str(exc)[:180])
            if item.get("time"):
                t = item["time"]
                await add_listing(f"/list-anime/release_year/{t['year']}/{((t['month'] - 1) // 3) * 3 + 1}")
            ranked = lambda: sorted((evaluate(item, value) for value in pool.values()), key=lambda value: value["score"], reverse=True)
            if not any(value["similarity"] == 1 for value in ranked()):
                queries = [item["name"]]
                short = re.split(r"[～~：:]|\s+(?:第|season|Season|\d+(?:st|nd|rd|th))", item["name"])[0].strip()
                if len(short) >= 3:
                    queries.append(short)
                queries.extend(aliases(item)[1:])
                for query in list(dict.fromkeys(queries))[:3]:
                    await add_listing("/search/animes", {"q": query}, "别名检索", pages=2)
                    if any(value["similarity"] == 1 for value in ranked()):
                        break
            checked = set()
            for _ in range(6):
                candidate = next((value for value in ranked() if value["id"] not in checked and value["similarity"] >= 0.48), None)
                if not candidate:
                    break
                identifier = candidate["id"]
                checked.add(identifier)
                try:
                    work = await self._page(f"/animes/{identifier}", identifier=identifier)
                    pool[identifier] = {**work, "method": pool[identifier]["method"]}
                    for related in work["related"]:
                        pool.setdefault(related["id"], {**related, "method": "同系列作品"})
                    # Check every exact-name contender, not just the first search hit.
                    if evaluate(item, work)["eligible"] and not any(c["similarity"] == 1 and c["id"] not in checked for c in ranked()):
                        break
                except Exception as exc:
                    errors.append(identifier + ": " + str(exc)[:180])
            all_candidates = [value for value in ranked() if value["similarity"] >= 0.48]
            candidates = all_candidates[:8]
            eligible = [value for value in all_candidates if value["eligible"]]
            unresolved = any(value["similarity"] == 1 and not value.get("verified") for value in all_candidates)
            status = "matched" if len(eligible) == 1 and not unresolved else "review" if candidates else "error" if errors else "not_found"
            result = self._save(item, {"status": status, "candidates": candidates, "methods": list(dict.fromkeys(methods + [c["method"] for c in candidates])), "errors": errors})
            return await self._apply(item, detail, result) if apply and status == "matched" else result

    async def _apply(self, item, detail, result):
        candidate = next(value for value in result["candidates"] if value["eligible"])
        try:
            saved = await asyncio.to_thread(self.store.save, item,
                {"filmarks": {"mode": "manual", "id": candidate["id"], "note": "自动匹配：" + "；".join(candidate["reasons"]) }},
                detail["revision"], self.repository.snapshot().entries, source="auto")
            analytics = AnalyticsStore(self.cache)
            await asyncio.to_thread(analytics.track, item["catalog_id"])
            await asyncio.to_thread(analytics.record, [merge_ratings(saved["item"], self.cache.all())])
            return self._save(item, {**result, "status": "applied", "applied_id": candidate["id"]})
        except MappingConflict as exc:
            return self._save(item, {**result, "status": "conflict", "errors": [*result["errors"], str(exc)]})
