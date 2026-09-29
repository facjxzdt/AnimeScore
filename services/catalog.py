"""Validated, locally cached bangumi-data catalog. Ratings live separately."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, ValidationError

from data.config import work_dir

SOURCE_URL = "https://raw.githubusercontent.com/bangumi-data/bangumi-data/master/dist/data.json"
ATTRIBUTION = {
    "name": "bangumi-data",
    "url": "https://github.com/bangumi-data/bangumi-data",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
}
CATALOG_TZ = timezone(timedelta(hours=8))
SEASONS = ("winter", "spring", "summer", "fall")
SITE_IDS = {
    "bangumi": "bgm_id", "mal": "mal_id", "aniList": "anilist_id",
    "anidb": "anidb_id", "tmdb": "tmdb_id", "bilibili": "bili_id",
    "filmarks": "filmarks_id", "anikore": "anikore_id",
}


class CatalogUnavailable(RuntimeError):
    pass


class SiteMeta(BaseModel):
    title: str
    urlTemplate: str
    type: str
    regions: list[str] = Field(default_factory=list)


class Site(BaseModel):
    site: str
    id: str = ""
    url: str | None = None
    begin: str | None = None
    end: str | None = None
    broadcast: str | None = None
    regions: list[str] | None = None
    comment: str | None = None


class Item(BaseModel):
    title: str = Field(min_length=1)
    titleTranslate: dict[str, list[str]] = Field(default_factory=dict)
    type: Literal["tv", "web", "movie", "ova"]
    lang: str
    officialSite: str = ""
    begin: str
    end: str = ""
    broadcast: str | None = None
    comment: str | None = None
    sites: list[Site]


class Dataset(BaseModel):
    siteMeta: dict[str, SiteMeta]
    items: list[Item] = Field(min_length=1)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=CATALOG_TZ) if parsed.tzinfo is None else parsed.astimezone(CATALOG_TZ)


def current_season(now: datetime | None = None) -> tuple[int, str]:
    now = (now or datetime.now(CATALOG_TZ)).astimezone(CATALOG_TZ)
    return now.year, SEASONS[(now.month - 1) // 3]


def normalize_title(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum())


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Catalog:
    def __init__(self, payload: dict):
        data = Dataset.model_validate(payload)
        self.entries = []
        self.by_site: dict[tuple[str, str], dict] = {}
        self.titles: list[tuple[str, ...]] = []
        for item in data.items:
            begin, end = parse_time(item.begin), parse_time(item.end)
            broadcast_start = None
            if item.broadcast:
                parts = item.broadcast.split("/")
                if len(parts) == 3:
                    broadcast_start = parse_time(parts[1])
            ids, links = {}, []
            for site in item.sites:
                meta = data.siteMeta.get(site.site)
                if not meta:
                    raise ValueError(f"Unknown site metadata: {site.site}")
                if site.site in SITE_IDS and site.id:
                    ids.setdefault(SITE_IDS[site.site], site.id)
                links.append({
                    **site.model_dump(exclude_none=True),
                    "title": meta.title, "type": meta.type,
                    "url": site.url or meta.urlTemplate.replace("{{id}}", quote(site.id, safe="/")),
                    "regions": site.regions if site.regions is not None else meta.regions,
                })
            translations = item.titleTranslate
            identity = json.dumps([item.title, item.begin, item.type, item.lang], ensure_ascii=False)
            entry = {
                "catalog_id": hashlib.sha256(identity.encode()).hexdigest()[:20],
                "name": item.title,
                "name_cn": next(iter(translations.get("zh-Hans", []) or translations.get("zh-Hant", [])), None),
                "name_en": next(iter(translations.get("en", [])), None),
                "titles": translations, "type": item.type, "language": item.lang,
                "official_site": item.officialSite or None,
                "begin": begin.isoformat() if begin else None,
                "end": end.isoformat() if end else None,
                "broadcast": item.broadcast or None,
                "comment": item.comment or None,
                "ids": ids, "sites": links, "data_source": "bangumi-data", "scores": {},
                "time": {"year": begin.year, "month": begin.month, "day": begin.day,
                         "weekday": (broadcast_start or begin).isoweekday()} if begin else None,
            }
            self.entries.append(entry)
            aliases = [item.title, *(alias for names in translations.values() for alias in names)]
            self.titles.append(tuple(filter(None, map(normalize_title, aliases))))
            for site in item.sites:
                if site.id:
                    self.by_site.setdefault((site.site, site.id), entry)

    def find(self, site: str, identifier: str) -> dict | None:
        return copy.deepcopy(self.by_site.get((site, str(identifier))))

    def season(self, year: int, season: str) -> list[dict]:
        quarter = SEASONS.index(season)
        return [copy.deepcopy(item) for item in self.entries
                if item["time"] and item["time"]["year"] == year
                and (item["time"]["month"] - 1) // 3 == quarter]

    @staticmethod
    def is_airing(item: dict, now: datetime | None = None) -> bool | None:
        now = now or datetime.now(CATALOG_TZ)
        begin, end = parse_time(item.get("begin")), parse_time(item.get("end"))
        if item["type"] not in {"tv", "web"} or not begin or begin > now:
            return False
        if end:
            return now <= end
        # An empty end is unknown, not evidence that a decades-old show still airs.
        return True if current_season(begin) == current_season(now) else None

    def airing(self, now: datetime | None = None) -> list[dict]:
        return [dict(copy.deepcopy(item), is_airing=True) for item in self.entries if self.is_airing(item, now)]

    def search(self, query: str, *, year=None, month=None, anime_type=None, match_mode="normal") -> list[dict]:
        needle = normalize_title(query)
        if not needle:
            return []
        matches = []
        for item, titles in zip(self.entries, self.titles):
            date = item["time"] or {}
            if year is not None and date.get("year") != year:
                continue
            if month is not None and date.get("month") != month:
                continue
            if anime_type and item["type"] != anime_type:
                continue
            if needle in titles:
                confidence = 1.0
            elif match_mode != "strict" and any(needle in title for title in titles):
                confidence = 0.9
            elif match_mode == "recall":
                confidence = max((SequenceMatcher(None, needle, title).ratio() for title in titles), default=0)
                if confidence < 0.6:
                    continue
            else:
                continue
            matches.append(dict(copy.deepcopy(item), confidence=confidence, matched_source=["bangumi-data"]))
        return sorted(matches, key=lambda item: (-item["confidence"], item["name"], item["catalog_id"]))


class CatalogRepository:
    def __init__(self, path: Path | str | None = None, url: str | None = None, max_age_hours: float = 24):
        self.path = Path(path or os.getenv("BANGUMI_DATA_PATH", str(Path(work_dir) / "data/cache/bangumi-data.json")))
        self.url = url or os.getenv("BANGUMI_DATA_URL", SOURCE_URL)
        self.max_age_hours = max_age_hours
        self._catalog: Catalog | None = None
        self._signature = None
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self.last_error: str | None = None
        self._read_error = False

    def snapshot(self) -> Catalog:
        with self._lock:
            try:
                stat = self.path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature != self._signature:
                    candidate = Catalog(json.loads(self.path.read_text(encoding="utf-8")))
                    self._catalog, self._signature = candidate, signature
                    self.last_error = None
                self._read_error = False
            except (OSError, ValueError, ValidationError) as exc:
                self.last_error = str(exc)
                self._read_error = True
            if self._catalog is None:
                raise CatalogUnavailable("bangumi-data is unavailable; run python -m scripts.sync_catalog or configure BANGUMI_DATA_PATH")
            return self._catalog

    def install(self, payload: dict) -> int:
        candidate = Catalog(payload)
        with self._lock:
            atomic_json(self.path, payload)
            stat = self.path.stat()
            self._catalog = candidate
            self._signature = (stat.st_mtime_ns, stat.st_size)
            self.last_error = None
            self._read_error = False
        return len(candidate.entries)

    def refresh(self, force: bool = False) -> tuple[bool, str]:
        # Slow downloads must not block readers of the last valid snapshot.
        with self._refresh_lock:
            try:
                self.snapshot()
                if not force and not self._read_error and self._signature and time.time() - self._signature[0] / 1e9 < self.max_age_hours * 3600:
                    return False, "Local catalog is fresh"
            except CatalogUnavailable:
                pass
            try:
                response = httpx.get(self.url, timeout=20, follow_redirects=True,
                                     headers={"User-Agent": "facjxzdt/AnimeScore (bangumi-data sync)"})
                response.raise_for_status()
                count = self.install(response.json())
                return True, f"Updated {count} catalog entries"
            except (httpx.HTTPError, OSError, ValueError) as exc:
                self.last_error = str(exc)
                return False, f"Catalog update failed: {exc}"

    def status(self) -> dict:
        try:
            count = len(self.snapshot().entries)
        except CatalogUnavailable:
            count = 0
        updated = self._signature[0] / 1e9 if self._signature else None
        return {"source": ATTRIBUTION, "available": bool(count), "total": count,
                "updated_at": datetime.fromtimestamp(updated, timezone.utc).isoformat() if updated else None,
                "stale": updated is None or time.time() - updated >= self.max_age_hours * 3600,
                "last_error": self.last_error}


@lru_cache(maxsize=1)
def get_repository() -> CatalogRepository:
    return CatalogRepository(max_age_hours=float(os.getenv("BANGUMI_DATA_MAX_AGE_HOURS", "24")))
