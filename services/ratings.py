"""Fetch ratings by catalog IDs with bounded requests and a persistent cache."""

from __future__ import annotations

import asyncio
import copy
import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from data import config
from services.mal import MALSource
from services.providers import PROVIDERS, normalize_id, site_url


class RatingPageUnavailable(ValueError):
    def __init__(self, status):
        self.http_status = status
        super().__init__("Upstream returned an access challenge")


def numeric_score(value, scale: float = 10) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return round(score * 10 / scale, 3) if math.isfinite(score) and 0 < score <= scale else None


def aggregate(scores: dict) -> float | None:
    configured = getattr(config, config.weights)
    keys = {"bgm": "bgm_score", "mal": "mal_score", "anilist": "anl_score",
            "anikore": "ank_score", "filmarks": "fm_score"}
    weighted = [(numeric_score(scores.get(name)), configured.get(key, 0)) for name, key in keys.items()]
    available = [(score, weight) for score, weight in weighted if score is not None and weight > 0]
    return round(sum(score * weight for score, weight in available) / sum(weight for _, weight in available), 3) if available else None


def weighted_score(scores: dict, weights: dict) -> float | None:
    available = [(numeric_score(scores.get(provider)), weight) for provider, weight in weights.items()
                 if weight > 0 and numeric_score(scores.get(provider)) is not None]
    return round(sum(score * weight for score, weight in available) / sum(weight for _, weight in available), 3) if available else None


class RatingCache:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or os.getenv("SCORE_CACHE_PATH", str(Path(config.work_dir) / "data/cache/ratings.sqlite3")))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS ratings (provider TEXT, id TEXT, payload TEXT NOT NULL, PRIMARY KEY (provider, id))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self, provider: str, identifier: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM ratings WHERE provider=? AND id=?", (provider, identifier)).fetchone()
        return json.loads(row[0]) if row else None

    def write(self, provider: str, identifier: str, value: dict):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO ratings VALUES (?, ?, ?)", (provider, identifier, json.dumps(value)))

    def all(self) -> dict:
        with self.connect() as db:
            return {(provider, identifier): json.loads(payload)
                    for provider, identifier, payload in db.execute("SELECT provider, id, payload FROM ratings")}


def merge_ratings(item: dict, ratings: dict, ttl: float = 3600) -> dict:
    result = copy.deepcopy(item)
    scores, statuses, votes, platform_ranks = {}, {}, {}, {}
    for provider, field in PROVIDERS.items():
        identifier = item.get("ids", {}).get(field)
        rating = ratings.get((provider, identifier)) if identifier else None
        if not identifier:
            statuses[provider] = {"status": "unmapped"}
        elif not rating:
            statuses[provider] = {"status": "not_fetched"}
        else:
            scores[provider] = rating["score"]
            votes[provider] = rating.get("votes")
            platform_ranks[provider] = rating.get("rank")
            for key, value in rating.get("details", {}).items():
                if value and not result.get(key):
                    result[key] = value
            updated = rating.get("updated_at")
            stale = updated is not None and time.time() - updated >= ttl
            statuses[provider] = {
                "rating_id": identifier,
                "status": "stale" if stale and rating["score"] is not None else rating["status"],
                "updated_at": datetime.fromtimestamp(updated, timezone.utc).isoformat() if updated else None,
                "error": rating.get("error"),
                "http_status": rating.get("http_status"),
                "source": rating.get("source"),
                "source_url": rating.get("source_url"),
                "source_errors": rating.get("source_errors"),
            }
    # Legacy extra scores can remain attached, but never invent a missing rating.
    scores = {**result.get("scores", {}), **scores}
    scores["total"] = aggregate(scores)
    result.update(scores=scores, score_status=statuses, votes=votes, platform_ranks=platform_ranks)
    return result


class RatingService:
    def __init__(self, cache: RatingCache, client: httpx.AsyncClient, ttl: float = 3600, intervals: dict | None = None):
        self.cache, self.client, self.ttl = cache, client, ttl
        self.locks = {provider: asyncio.Lock() for provider in PROVIDERS}
        self.last_request = dict.fromkeys(PROVIDERS, 0.0)
        self.blocked_until = dict.fromkeys(PROVIDERS, 0.0)
        self.intervals = {"bgm": 0.1, "mal": 2.0, "anilist": 2.2, "filmarks": 3.0, "anikore": 3.0}
        if intervals is not None:
            self.intervals.update(intervals)
        self.mal = MALSource(client, self.intervals["mal"])

    async def _fetch(self, provider: str, identifier: str) -> dict:
        identifier = normalize_id(provider, identifier)
        if provider == "mal":
            return await self.mal.fetch(identifier)
        if provider in {"filmarks", "anikore"}:
            from services.scrapers import parse_rating
            response = await self.client.get(site_url(provider, identifier), follow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200:
                raise RatingPageUnavailable(response.status_code)
            return await asyncio.to_thread(parse_rating, provider, response.text)
        if provider == "bgm":
            response = await self.client.get(f"https://api.bgm.tv/v0/subjects/{identifier}")
        else:
            response = await self.client.post("https://graphql.anilist.co", json={
                "query": "query ($id: Int) { Media(id: $id, type: ANIME) { title { romaji } meanScore averageScore episodes coverImage { large } stats { scoreDistribution { score amount } } } }",
                "variables": {"id": int(identifier)},
            })
        response.raise_for_status()
        payload = response.json()
        if provider == "bgm":
            return {"score": numeric_score(payload["rating"]["score"]),
                    "votes": payload["rating"].get("total"), "rank": payload["rating"].get("rank"), "title": payload.get("name"),
                    "details": {"poster": (payload.get("images") or {}).get("large"),
                                "summary": payload.get("summary"), "episodes": payload.get("total_episodes") or payload.get("eps")}}
        media = payload["data"]["Media"]
        values = [score for value in (media.get("meanScore"), media.get("averageScore"))
                  if (score := numeric_score(value, 100)) is not None]
        distribution = (media.get("stats") or {}).get("scoreDistribution")
        return {"score": round(sum(values) / len(values), 3) if values else None, "title": (media.get("title") or {}).get("romaji"),
                "votes": sum(point.get("amount", 0) for point in distribution) if distribution else None,
                "rank": None,
                "details": {"poster": (media.get("coverImage") or {}).get("large"), "episodes": media.get("episodes")}}

    async def get(self, provider: str, identifier: str) -> dict:
        # A provider lock also coalesces identical concurrent requests after a cache miss.
        async with self.locks[provider]:
            cached = await asyncio.to_thread(self.cache.read, provider, identifier)
            if cached and time.time() < cached["retry_at"] and "details" in cached:
                return cached
            delay = max(self.intervals[provider] - (time.monotonic() - self.last_request[provider]),
                        self.blocked_until[provider] - time.time())
            if delay > 0 and provider != "mal":
                await asyncio.sleep(delay)
            self.last_request[provider] = time.monotonic()
            try:
                data = await self._fetch(provider, identifier)
                now = time.time()
                result = {**data, "status": "ok" if data["score"] is not None else "no_score",
                          "updated_at": now, "retry_at": now + self.ttl}
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else getattr(exc, "http_status", None)
                retry_at = max(time.time() + 60, getattr(exc, "retry_at", 0))
                if status == 429 and provider != "mal":
                    retry_after = exc.response.headers.get("Retry-After", "60")
                    try:
                        seconds = float(retry_after)
                        if math.isfinite(seconds):
                            retry_at = max(retry_at, time.time() + seconds)
                    except ValueError:
                        try:
                            retry_at = max(retry_at, parsedate_to_datetime(retry_after).timestamp())
                        except (TypeError, ValueError, OverflowError):
                            pass
                    self.blocked_until[provider] = retry_at
                result = {**(cached or {}), "score": cached["score"] if cached else None,
                          "details": cached.get("details", {}) if cached else {},
                          "updated_at": cached.get("updated_at") if cached else None,
                          "status": "stale" if cached and cached["score"] is not None else "unavailable",
                          "error": f"HTTP {status}" if status else type(exc).__name__,
                          "http_status": status, "retry_at": retry_at}
                if provider == "mal":
                    result["source_errors"] = getattr(exc, "source_errors", [])
            await asyncio.to_thread(self.cache.write, provider, identifier, result)
            return result

    async def enrich(self, items: list[dict]) -> list[dict]:
        from services.mappings import MappingStore
        items = await asyncio.to_thread(MappingStore(self.cache).apply, items)
        keys = {(provider, item["ids"][field]) for item in items for provider, field in PROVIDERS.items()
                if item.get("ids", {}).get(field)}
        values = await asyncio.gather(*(self.get(*key) for key in keys))
        ratings = dict(zip(keys, values))
        result = [merge_ratings(item, ratings, self.ttl) for item in items]
        from services.analytics import AnalyticsStore
        await asyncio.to_thread(AnalyticsStore(self.cache).record, result)
        return result
