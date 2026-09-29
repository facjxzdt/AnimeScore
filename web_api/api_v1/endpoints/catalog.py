"""Data provenance and freshness, including degraded/offline operation."""

from fastapi import APIRouter

from services.catalog import get_repository

router = APIRouter()


@router.get("/")
def catalog_status():
    return get_repository().status()
