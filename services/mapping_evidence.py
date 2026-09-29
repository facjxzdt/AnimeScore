"""Fetch bounded work metadata from fixed provider endpoints, never user URLs."""

import asyncio
import json
import time

import httpx
from bs4 import BeautifulSoup

from services.filmarks_mapping import parse_work
from services.http import retry_deadline
from services.mal import parse_page, parse_jikan
from services.providers import normalize_id, site_url
from services.scrapers import parse_rating


def titles(values):
    return list(dict.fromkeys(value[:300] for value in values if isinstance(value, str) and value.strip()))[:15]


def mal_page(html, identifier):
    rating = parse_page(html, identifier)
    soup = BeautifulSoup(html, "html.parser")
    labels = {node.get_text(strip=True): node.parent.get_text(" ", strip=True).partition(":")[2].strip()
              for node in soup.select("span.dark_text")}
    return {"titles": titles([rating["title"], labels.get("Japanese:"), labels.get("English:"), labels.get("Synonyms:")]),
            "date": labels.get("Aired:"), "format": labels.get("Type:"), "episodes": rating["details"].get("episodes"), "media_type": "anime"}


class MappingEvidence:
    def __init__(self, ratings):
        self.ratings, self.cache = ratings, ratings.cache
        with self.cache.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS mapping_evidence (provider TEXT, identifier TEXT, updated_at REAL, payload TEXT, PRIMARY KEY(provider,identifier))")

    async def request(self, provider, url, **kwargs):
        if self.ratings.blocked_until[provider] > time.time():
            raise ValueError("Provider is cooling down")
        delay = self.ratings.intervals[provider] - (time.monotonic() - self.ratings.last_request[provider])
        if delay > 0:
            await asyncio.sleep(delay)
        self.ratings.last_request[provider] = time.monotonic()
        response = await self.ratings.client.request("POST" if "json" in kwargs else "GET", url, follow_redirects=False, timeout=15, **kwargs)
        if response.status_code in {403, 429}:
            self.ratings.blocked_until[provider] = retry_deadline(response.headers.get("Retry-After", "300"), minimum=300)
        response.raise_for_status()
        if response.status_code != 200 or len(response.content) > 4_000_000:
            raise ValueError("Invalid work response")
        return response

    async def get(self, provider, identifier):
        identifier = normalize_id(provider, identifier)
        with self.cache.connect() as db:
            row = db.execute("SELECT updated_at,payload FROM mapping_evidence WHERE provider=? AND identifier=?", (provider, identifier)).fetchone()
        if row and row[0] > time.time() - 86400:
            return json.loads(row[1])
        async with self.ratings.locks[provider]:
            data = await self._fetch(provider, identifier)
        if not data.get("titles"):
            raise ValueError("Work title missing")
        if isinstance(data.get("date"), dict):
            data["date"] = {key: data["date"].get(key) if isinstance(data["date"].get(key), int) else None for key in ("year", "month", "day")}
        elif data.get("date"):
            data["date"] = str(data["date"])[:120]
        for field, limit in (("format", 120), ("official_site", 500)):
            if data.get(field):
                data[field] = str(data[field])[:limit]
        if not isinstance(data.get("episodes"), int):
            data["episodes"] = None
        data = {**data, "provider": provider, "id": identifier, "url": site_url(provider, identifier), "verified": True}
        with self.cache.connect() as db:
            db.execute("INSERT OR REPLACE INTO mapping_evidence VALUES (?,?,?,?)", (provider, identifier, time.time(), json.dumps(data)))
        return data

    async def _fetch(self, provider, identifier):
        if provider == "bgm":
            response = await self.request(provider, f"https://api.bgm.tv/v0/subjects/{identifier}")
            data = response.json()
            if str(data["id"]) != identifier:
                raise ValueError("Wrong work ID")
            return {"titles": titles([data.get("name"), data.get("name_cn")]), "date": data.get("date"),
                    "format": data.get("platform"), "episodes": data.get("eps"), "media_type": "anime" if data["type"] == 2 else "other"}
        if provider == "anilist":
            response = await self.request(provider, "https://graphql.anilist.co", json={
                "query": "query ($id:Int) { Media(id:$id,type:ANIME) { id type title { romaji english native } synonyms format episodes startDate { year month day } } }",
                "variables": {"id": int(identifier)}})
            data = response.json()["data"]["Media"]
            if str(data["id"]) != identifier or data["type"] != "ANIME":
                raise ValueError("Wrong work ID or media type")
            day = data.get("startDate") or {}
            return {"titles": titles([*data["title"].values(), *(data.get("synonyms") or [])]), "date": day,
                    "format": data.get("format"), "episodes": data.get("episodes"), "media_type": "anime"}
        if provider == "mal":
            try:
                response = await self.ratings.mal._request("myanimelist", site_url(provider, identifier))
                return await asyncio.to_thread(mal_page, response.text, identifier)
            except (ValueError, KeyError, TypeError, httpx.HTTPError):
                # The independent Jikan endpoint can supply metadata when MAL is unavailable.
                pass
            response = await self.ratings.mal._request("jikan", f"https://api.jikan.moe/v4/anime/{identifier}")
            data = response.json()
            parse_jikan(data, identifier)
            work = data["data"]
            return {"titles": titles([work.get("title"), *(entry.get("title") for entry in work.get("titles", []))]),
                    "date": (work.get("aired") or {}).get("from"), "format": work.get("type"),
                    "episodes": work.get("episodes"), "media_type": "anime"}
        response = await self.request(provider, site_url(provider, identifier))
        if provider == "filmarks":
            data = await asyncio.to_thread(parse_work, response.text, identifier)
            return {"titles": titles([data["title"]]), "date": data["date"], "format": "TVSeason (TV/WEB/OVA)",
                    "official_site": data.get("official_site"), "media_type": "anime"}
        soup = BeautifulSoup(response.text, "html.parser")
        canonical = soup.select_one('link[rel="canonical"]')
        if not canonical or normalize_id(provider, canonical.get("href", "")) != identifier:
            raise ValueError("Work canonical ID mismatch")
        rating = parse_rating(provider, response.text)
        return {"titles": titles([rating.get("title")]), "date": None, "format": None, "media_type": "anime"}
