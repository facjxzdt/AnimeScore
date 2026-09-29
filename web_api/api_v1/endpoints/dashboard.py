"""Web-facing rankings and history; weights never mutate shared observations."""

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from services.analytics import AnalyticsStore, rank_items, summarize
from services.catalog import SEASONS, current_season, get_repository
from services.ratings import weighted_score
from services.providers import PROVIDERS, public_providers
from services.mappings import MappingStore
from web_api.api_v1.deps import cached_items, get_score_cache

router = APIRouter()
Period = Literal["7d", "30d", "90d", "1y"]


def weights(
    bgm: float = Query(5, ge=0, le=100, allow_inf_nan=False),
    mal: float = Query(2, ge=0, le=100, allow_inf_nan=False),
    anilist: float = Query(0, ge=0, le=100, allow_inf_nan=False),
    filmarks: float = Query(0, ge=0, le=100, allow_inf_nan=False),
    anikore: float = Query(0, ge=0, le=100, allow_inf_nan=False),
):
    if bgm + mal + anilist + filmarks + anikore == 0:
        raise HTTPException(422, "At least one platform weight must be positive")
    return {"bgm": bgm, "mal": mal, "anilist": anilist, "filmarks": filmarks, "anikore": anikore}


def store():
    return AnalyticsStore(get_score_cache())


def find_item(catalog_id):
    item = next((item for item in get_repository().snapshot().entries if item["catalog_id"] == catalog_id), None)
    if not item:
        raise HTTPException(404, "Anime not found in catalog")
    return MappingStore(get_score_cache()).apply([item])[0]


@router.get("/ranking")
def ranking(
    q: str = Query("", max_length=200),
    year: int | None = Query(None, ge=1900, le=2200),
    season: Literal["winter", "spring", "summer", "fall"] | None = None,
    anime_type: Literal["tv", "web", "movie", "ova"] | None = None,
    min_platforms: int = Query(0, ge=0, le=5), min_votes: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    weighting: dict = Depends(weights),
):
    catalog = get_repository().snapshot()
    year = year or current_season()[0]
    season = season or current_season()[1]
    selected = catalog.search(q.strip(), anime_type=anime_type) if q.strip() else catalog.season(year, season)
    if anime_type:
        selected = [item for item in selected if item["type"] == anime_type]
    items = rank_items(cached_items(selected), weighting, min_platforms, min_votes)
    for item in items:
        item.pop("sites", None)
        item.pop("summary", None)
    return {"items": items[offset:offset + limit], "total": len(items), "offset": offset, "limit": limit,
            "summary": summarize(items), "weights": weighting, "query": q.strip(),
            "season": {"year": year, "season": season}, "collection": store().status()}


@router.get("/status")
def status(request: Request):
    catalog = get_repository().snapshot()
    years = sorted({item["time"]["year"] for item in catalog.entries if item["time"]}, reverse=True)
    return {"catalog": get_repository().status(), "collection": store().status(),
            "mapping_updated_at": MappingStore(get_score_cache()).updated_at(),
            "enabled": request.app.state.collector.enabled, "years": years,
            "current_year": current_season()[0], "current_season": current_season()[1],
            "providers": public_providers()}


@router.get("/anime/{catalog_id}")
async def detail(catalog_id: str, request: Request, refresh: bool = True, weighting: dict = Depends(weights)):
    item = await run_in_threadpool(find_item, catalog_id)
    await run_in_threadpool(store().track, catalog_id)
    result = (await request.app.state.ratings.enrich([item]))[0] if refresh else (await run_in_threadpool(cached_items, [item]))[0]
    result["scores"]["total"] = weighted_score(result["scores"], weighting)
    return result


@router.get("/anime/{catalog_id}/history")
def history(catalog_id: str, period: Period = "7d", weighting: dict = Depends(weights)):
    return store().history(find_item(catalog_id), period, weighting)


@router.get("/anime/{catalog_id}/history.csv")
def export_history(catalog_id: str, period: Period = "30d", weighting: dict = Depends(weights)):
    data = store().history(find_item(catalog_id), period, weighting)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["timestamp_utc", *PROVIDERS, "total", *(f"{p}_votes" for p in PROVIDERS), "weights"])
    for point in data["points"]:
        writer.writerow([point["timestamp"], *(point["scores"].get(p) for p in (*PROVIDERS, "total")),
                         *(point["votes"].get(p) for p in PROVIDERS),
                         ";".join(f"{p}={weighting[p]}" for p in PROVIDERS)])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="scores-{catalog_id}-{period}.csv"'})
