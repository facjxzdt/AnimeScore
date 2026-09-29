"""Authenticated submissions expose only the current user's review records."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from services.auth import require_user
from services.catalog import get_repository

router = APIRouter()


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_id: str = Field(pattern=r"^[a-f0-9]{20}$")
    provider: Literal["bgm", "mal", "anilist", "filmarks", "anikore"]
    id: str = Field(min_length=1, max_length=300)


@router.get("")
def list_submissions(request: Request, response: Response, user=Depends(require_user), offset: int = Query(0, ge=0), catalog_id: str | None = Query(None, max_length=20)):
    response.headers["Cache-Control"] = "no-store"
    service = request.app.state.contributions
    names = {value["catalog_id"]: value.get("name_cn") or value["name"] for value in get_repository().snapshot().entries}
    items = service.list(user["id"], offset=offset, catalog_id=catalog_id)
    return {"items": [{**item, "anime_name": names.get(item["catalog_id"], item["catalog_id"])} for item in items], "quota": service.quota(user["id"])}


@router.get("/{submission_id}")
def submission(submission_id: str, request: Request, response: Response, user=Depends(require_user)):
    response.headers["Cache-Control"] = "no-store"
    service = request.app.state.contributions
    return {"submission": service.get(submission_id, user["id"]), "quota": service.quota(user["id"])}


@router.post("", status_code=202)
def submit(body: Submission, request: Request, user=Depends(require_user)):
    item = next((value for value in get_repository().snapshot().entries if value["catalog_id"] == body.catalog_id), None)
    if not item:
        raise HTTPException(404, "动画不存在")
    service = request.app.state.contributions
    result = service.submit(user, item, body.provider, body.id)
    return {"submission": result, "quota": service.quota(user["id"])}
