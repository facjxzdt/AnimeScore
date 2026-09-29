"""Authenticated mapping management, with loopback-only local administration."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from services.analytics import AnalyticsStore
from services.auth import authorize_admin as authorize, current_user
from services.catalog import get_repository, current_season
from services.mappings import MappingConflict, MappingStore
from services.providers import PROVIDERS, normalize_id, public_providers, site_url
from web_api.api_v1.deps import get_score_cache


router = APIRouter(dependencies=[Depends(authorize)])


def store():
    return MappingStore(get_score_cache())


def find(catalog_id):
    item = next((item for item in get_repository().snapshot().entries if item["catalog_id"] == catalog_id), None)
    if not item:
        raise HTTPException(404, "动画不存在")
    return item


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["catalog", "manual", "disabled"]
    id: str = Field("", max_length=300)
    note: str = Field("", max_length=500)


class Changes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    changes: dict[str, Change] = Field(min_length=1, max_length=5)


class Validation(BaseModel):
    provider: Literal["bgm", "mal", "anilist", "filmarks", "anikore"]
    id: str = Field(min_length=1, max_length=300)


@router.get("/status")
def status(mode: str = Depends(authorize)):
    return {"mode": mode, "providers": public_providers()}


@router.get("/mappings")
def mappings(request: Request, q: str = Query("", max_length=200), missing: str = "", edited: bool = False, filmarks_status: str = "",
             limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    if missing and missing not in PROVIDERS:
        raise HTTPException(422, "未知站点")
    catalog = get_repository().snapshot()
    query = q.strip()
    by_id = query.replace("/", "").isdigit()
    items = store().apply(catalog.search(query) if query and not by_id else catalog.entries)
    if by_id:
        items = [item for item in items if query in item["ids"].values() or query in item["base_ids"].values()]
    if missing:
        items = [item for item in items if not item["ids"].get(PROVIDERS[missing])]
    if edited:
        items = [item for item in items if any(value in {"manual", "disabled"} for value in item["mapping_sources"].values())]
    matches = request.app.state.filmarks_mapper.results()
    if filmarks_status:
        items = [item for item in items if matches.get(item["catalog_id"], {}).get("status", "unchecked") == filmarks_status]
    items.sort(key=lambda item: (item.get("begin") or "", item["name"]), reverse=True)
    keys = ("catalog_id", "name", "name_cn", "type", "time", "ids", "base_ids", "mapping_sources", "mapping_revision", "mapping_contributors")
    return {"items": [{**{key: item.get(key) for key in keys}, "filmarks_status": matches.get(item["catalog_id"], {}).get("status", "unchecked")} for item in items[offset:offset + limit]], "total": len(items)}


@router.get("/mappings/export")
def export():
    return store().export()


@router.get("/mappings/{catalog_id}")
def mapping(catalog_id: str, request: Request):
    item = find(catalog_id)
    return {**store().detail(item), "filmarks_match": request.app.state.filmarks_mapper.result(item)}


@router.put("/mappings/{catalog_id}")
def save_mapping(catalog_id: str, body: Changes, request: Request):
    item = find(catalog_id)
    try:
        result = store().save(item, {p: change.model_dump() for p, change in body.changes.items()},
                              body.revision, get_repository().snapshot().entries)
    except MappingConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    AnalyticsStore(get_score_cache()).track(catalog_id)
    return {**result, "filmarks_match": request.app.state.filmarks_mapper.result(item)}


@router.post("/validate")
async def validate_mapping(body: Validation, request: Request):
    try:
        identifier = normalize_id(body.provider, body.id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    rating = await request.app.state.ratings.get(body.provider, identifier)
    return {"id": identifier, "url": site_url(body.provider, identifier), **rating}


@router.post("/mappings/{catalog_id}/collect")
async def collect_mapping(catalog_id: str, request: Request):
    item = await run_in_threadpool(find, catalog_id)
    return (await request.app.state.ratings.enrich([item]))[0]


class MappingBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["season", "missing"] = "season"
    year: int | None = Field(None, ge=1900, le=2200)
    season: Literal["winter", "spring", "summer", "fall"] | None = None
    limit: int = Field(100, ge=1, le=250)
    apply: bool = True
    force: bool = False


@router.get("/filmarks/job")
def mapping_job(request: Request):
    return request.app.state.filmarks_jobs.status()


@router.post("/filmarks/job")
def start_mapping_job(body: MappingBatch, request: Request):
    catalog = get_repository().snapshot()
    items = catalog.season(body.year or current_season()[0], body.season or current_season()[1]) if body.scope == "season" else catalog.entries
    # Previously unexamined titles first; repeated batches can advance through the full catalog.
    matches = request.app.state.filmarks_mapper.results()
    items = sorted(items, key=lambda item: matches.get(item["catalog_id"], {}).get("checked_at", 0))
    try:
        return request.app.state.filmarks_jobs.start(items, apply=body.apply, force=body.force, limit=body.limit)
    except MappingConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/filmarks/job/cancel")
def cancel_mapping_job(request: Request):
    return request.app.state.filmarks_jobs.cancel()


@router.post("/filmarks/discover/{catalog_id}")
async def discover_mapping(catalog_id: str, request: Request):
    item = await run_in_threadpool(find, catalog_id)
    return await request.app.state.filmarks_mapper.discover(item, force=True)


class RoleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "admin"]


def actor(request, mode):
    user = current_user(request)
    return str(user["id"]) if mode == "bangumi" and user else mode


@router.get("/users")
def users(request: Request, q: str = Query("", max_length=100), offset: int = Query(0, ge=0)):
    return {"items": request.app.state.auth.users(q, offset)}


@router.put("/users/{user_id}/role")
def set_role(user_id: int, body: RoleChange, request: Request, mode=Depends(authorize)):
    request.app.state.auth.set_role(user_id, body.role, actor(request, mode))
    return {"ok": True}


@router.get("/contributions")
def contributions(request: Request, offset: int = Query(0, ge=0)):
    items = request.app.state.contributions.list(offset=offset)
    names = {value["catalog_id"]: value.get("name_cn") or value["name"] for value in get_repository().snapshot().entries}
    return {"items": [{**item, "anime_name": names.get(item["catalog_id"], item["catalog_id"])} for item in items]}


@router.post("/contributions/{submission_id}/approve")
def approve_contribution(submission_id: str, request: Request, mode=Depends(authorize)):
    return request.app.state.contributions.approve(submission_id, actor(request, mode))
