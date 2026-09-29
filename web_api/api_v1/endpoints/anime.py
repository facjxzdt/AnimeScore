"""Anime resources from the shared bangumi-data catalog."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from services.catalog import Catalog, current_season, get_repository
from services.ratings import RatingService
from web_api.api_v1 import schemas
from web_api.api_v1.deps import cached_items, get_airing_items, get_rating_service, get_subscribed_items, get_score_cache
from services.mappings import MappingStore

router = APIRouter()
Sort = Literal["score", "name", "time"]
Season = Literal["winter", "spring", "summer", "fall"]


def sort_items(items: list[dict], sort_by: str) -> list[dict]:
    if sort_by == "score":
        return sorted(items, key=lambda item: (-(item.get("scores", {}).get("total") or 0), item["name"]))
    if sort_by == "time":
        return sorted(items, key=lambda item: (item.get("begin") or "", item["name"]), reverse=True)
    return sorted(items, key=lambda item: item["name"])


def list_response(items, limit, offset, sort_by):
    ordered = sort_items(items, sort_by)
    selected = ordered[offset:offset + limit] if limit else ordered[offset:]
    return schemas.AnimeListResponse(items=selected, total=len(items),
                                     page=offset // limit + 1 if limit else 1, page_size=limit or len(selected))


@router.get("/", response_model=schemas.AnimeListResponse)
def list_anime(
    year: Optional[int] = Query(None, ge=1900, le=2200),
    month: Optional[int] = Query(None, ge=1, le=12),
    anime_type: Optional[Literal["tv", "web", "movie", "ova"]] = None,
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), sort_by: Sort = "time",
):
    items = [item for item in get_repository().snapshot().entries
             if (year is None or (item["time"] or {}).get("year") == year)
             and (month is None or (item["time"] or {}).get("month") == month)
             and (anime_type is None or item["type"] == anime_type)]
    return list_response(cached_items(items), limit, offset, sort_by)


@router.get("/airing", response_model=schemas.AnimeListResponse)
def get_airing_anime(limit: Optional[int] = Query(None, ge=1, le=100),
                     sort_by: Sort = "score", offset: int = Query(0, ge=0)):
    return list_response(get_airing_items(), limit, offset, sort_by)


@router.get("/subscribed", response_model=schemas.AnimeListResponse)
def get_subscribed_anime(limit: Optional[int] = Query(None, ge=1, le=100),
                         sort_by: Sort = "score", offset: int = Query(0, ge=0)):
    return list_response(get_subscribed_items(), limit, offset, sort_by)


def season_response(year: int, season: str):
    repository = get_repository()
    items = cached_items(repository.snapshot().season(year, season))
    for item in items:
        item["is_airing"] = Catalog.is_airing(item)
    return schemas.AnimeSeasonResponse(
        season=schemas.SeasonInfo(year=year, season=season, name=f"{year} {season}"),
        anime_list=sort_items(items, "score"), total=len(items), updated_at=repository.status()["updated_at"],
    )


@router.get("/season/current", response_model=schemas.AnimeSeasonResponse)
def get_current_season():
    return season_response(*current_season())


@router.get("/season/{year}/{season}", response_model=schemas.AnimeSeasonResponse)
def get_season(year: int, season: Season):
    return season_response(year, season)


@router.get("/{bgm_id}", response_model=schemas.AnimeInfo)
async def get_anime_by_id(bgm_id: str, include_scores: bool = True,
                         ratings: RatingService = Depends(get_rating_service)):
    catalog = await run_in_threadpool(get_repository().snapshot)
    mapped = await run_in_threadpool(MappingStore(get_score_cache()).apply, catalog.entries)
    item = next((entry for entry in mapped if entry["ids"].get("bgm_id") == bgm_id), None)
    if not item:
        item = next((entry for entry in get_subscribed_items() if entry["ids"].get("bgm_id") == bgm_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Anime with bgm_id {bgm_id} not found")
    if item.get("data_source") == "bangumi-data":
        item["is_airing"] = Catalog.is_airing(item)
    return (await ratings.enrich([item]))[0] if include_scores else (await run_in_threadpool(cached_items, [item]))[0]
