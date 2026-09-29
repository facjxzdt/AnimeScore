"""Shared data access for catalog, subscriptions and cached ratings."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import Request

from data.config import work_dir
from services.catalog import CatalogUnavailable, get_repository
from services.ratings import RatingCache, RatingService, aggregate, merge_ratings, numeric_score
from services.mappings import MappingStore


@lru_cache(maxsize=1)
def get_score_cache() -> RatingCache:
    return RatingCache()


def get_rating_service(request: Request) -> RatingService:
    return request.app.state.ratings


def get_anime_score():
    from web_api.wrapper import AnimeScore
    return AnimeScore()


def cached_items(items: list[dict]) -> list[dict]:
    ratings = get_score_cache().all()
    items = MappingStore(get_score_cache()).apply(items)
    return [merge_ratings(item, ratings) for item in items]


def get_airing_items() -> list[dict]:
    return cached_items(get_repository().snapshot().airing())


def get_subscribed_items() -> list[dict]:
    data = get_subscribed_list()
    try:
        catalog = get_repository().snapshot()
    except CatalogUnavailable:
        catalog = None
    items = []
    for name, info in data.items():
        if not isinstance(info, dict):
            continue
        legacy = convert_single_anime(name, info)
        bgm_id = legacy["ids"].get("bgm_id")
        entry = catalog.find("bangumi", bgm_id) if catalog and bgm_id else None
        if entry:
            # Keep saved enrichment while catalog titles, dates and IDs stay authoritative.
            scores = legacy["scores"]
            legacy.update(entry)
            legacy["scores"] = scores
        legacy["is_subscribed"] = True
        items.append(legacy)
    return cached_items(items)


def get_subscribed_list() -> dict:
    path = Path(work_dir) / "data/jsons/sub_score_sorted.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get_airing_list() -> dict:
    """Compatibility view for older Python callers, now backed by bangumi-data."""
    return {item["catalog_id"]: item for item in get_airing_items()}


def clear_cache():
    # Catalog and SQLite changes are observed on the next read.
    pass


def convert_single_anime(name: str, info: dict) -> dict:
    def identifier(value):
        return str(value) if value not in (None, "", "None", "Error", "N/A", "-") else None

    ids = info.get("ids") or {}
    scores = {key: numeric_score(info.get(old)) for key, old in {
        "bgm": "bgm_score", "mal": "mal_score", "anilist": "anl_score",
        "anikore": "ank_score", "filmarks": "fm_score",
    }.items()}
    scores["total"] = aggregate(scores)
    return {
        "name": info.get("name", name), "name_cn": info.get("name_cn"), "name_en": info.get("name_en"),
        "ids": {"bgm_id": identifier(info.get("bgm_id") or ids.get("bgm_id")),
                "mal_id": identifier(ids.get("mal_id")), "anilist_id": identifier(ids.get("anl_id")),
                "anikore_id": identifier(ids.get("ank_id")), "filmarks_id": identifier(ids.get("fm_id"))},
        "scores": scores, "time": info.get("time") or None,
        **{field: info.get(field) for field in ("poster", "studio", "director", "source", "summary")},
    }
