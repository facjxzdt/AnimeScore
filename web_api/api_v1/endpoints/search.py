#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search APIs
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from services.catalog import CatalogUnavailable, get_repository
from services.ratings import RatingService
from web_api.api_v1 import schemas
from web_api.api_v1.deps import cached_items, get_rating_service

router = APIRouter()


@router.get("/", response_model=schemas.AnimeSearchResponse)
async def search_anime(
    q: str = Query(..., min_length=1, description="Search keyword"),
    source: Literal["bangumi-data", "precise", "bangumi"] = "bangumi-data",
    year: Optional[int] = Query(None, ge=1900, le=2200, description="Year filter"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month filter"),
    studio: Optional[str] = Query(None, description="Studio filter"),
    director: Optional[str] = Query(None, description="Director filter"),
    source_type: Optional[str] = Query(None, description="Source type filter"),
    match_mode: Literal["normal", "recall", "strict"] = "normal",
    extra_scores: bool = Query(False, description="Include Anikore/Filmarks scores"),
    debug_scores: bool = Query(False, description="Include debug details for extra scores"),
    limit: int = Query(10, ge=1, le=50, description="Limit"),
    offset: int = Query(0, ge=0),
    anime_type: Optional[Literal["tv", "web", "movie", "ova"]] = None,
    include_scores: bool = False,
    ratings: RatingService = Depends(get_rating_service),
):
    """
    Search anime by keyword.
    """
    filters_applied = {}
    results = []
    q = q.strip()
    if not q:
        raise HTTPException(status_code=422, detail="Search keyword cannot be blank")

    if source == "bangumi-data":
        if studio or director or source_type or extra_scores:
            raise HTTPException(status_code=400, detail="studio/director/source_type/extra_scores require source=precise")
        filters = {"year": year, "month": month, "anime_type": anime_type}
        catalog = await run_in_threadpool(get_repository().snapshot)
        matches = await run_in_threadpool(catalog.search, q, **filters, match_mode=match_mode)
        selected = matches[offset:offset + limit]
        items = await ratings.enrich(selected) if include_scores else await run_in_threadpool(cached_items, selected)
        return schemas.AnimeSearchResponse(query=q, source=source, results=items, total=len(matches),
                                           filters_applied={k: v for k, v in filters.items() if v is not None} or None)

    try:
        if source == "precise":
            from apis.precise import search_anime_precise_async
            filters = {
                "year": year,
                "month": month,
                "studio": studio,
                "director": director,
                "source": source_type,
            }
            filters = {k: v for k, v in filters.items() if v is not None}
            filters_applied = filters

            precise_results = await search_anime_precise_async(
                q,
                **filters,
                include_extra_scores=extra_scores,
                debug_scores=debug_scores,
                match_mode=match_mode,
                top_n=limit + offset,
            )

            for item in precise_results:
                result = schemas.AnimeSearchResult(
                    name=item.get("name", ""),
                    name_cn=item.get("name_cn"),
                    name_en=item.get("name_en"),
                    ids=schemas.AnimeIDs(
                        bgm_id=item.get("bgm_id"),
                        mal_id=item.get("mal_id"),
                        anilist_id=item.get("anilist_id"),
                        anikore_id=item.get("ank_id"),
                        filmarks_id=item.get("fm_id"),
                        douban_id=item.get("douban_id"),
                        bili_id=item.get("bili_id"),
                        anidb_id=item.get("anidb_id"),
                        tmdb_id=item.get("tmdb_id"),
                        imdb_id=item.get("imdb_id"),
                        tvdb_id=item.get("tvdb_id"),
                        wikidata_id=item.get("wikidata_id"),
                    ),
                    scores=schemas.AnimeScores(
                        bgm=item.get("bgm_score"),
                        mal=item.get("mal_score"),
                        anilist=item.get("anilist_score"),
                        anikore=item.get("ank_score"),
                        filmarks=item.get("fm_score"),
                    ),
                    time=schemas.AnimeTime(
                        year=item.get("year"),
                        month=item.get("month"),
                    ),
                    studio=item.get("studio"),
                    director=item.get("director"),
                    source=item.get("source"),
                    summary=item.get("summary"),
                    confidence=item.get("confidence"),
                    matched_source=[
                        s for s, v in {
                            "bangumi": item.get("bgm_id"),
                            "anilist": item.get("anilist_id"),
                            "mal": item.get("mal_id"),
                        }.items() if v
                    ],
                    debug_scores=item.get("debug_scores"),
                )
                results.append(result)

        elif source == "bangumi":
            from apis.bangumi import Bangumi
            bgm_results = await Bangumi().search_anime_async(q)

            if isinstance(bgm_results, dict) and "data" in bgm_results:
                for item in bgm_results["data"]:
                    result = schemas.AnimeSearchResult(
                        name=item.get("name", ""),
                        name_cn=item.get("name_cn"),
                        ids=schemas.AnimeIDs(bgm_id=str(item.get("id"))),
                        scores=schemas.AnimeScores(bgm=item.get("score")),
                        poster=item.get("images", {}).get("large") if item.get("images") else None,
                        confidence=0.8,
                        matched_source=["bangumi"],
                    )
                    results.append(result)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown search source: {source}")

    except (HTTPException, CatalogUnavailable):
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return schemas.AnimeSearchResponse(
        query=q,
        source=source,
        results=results[offset:offset + limit],
        total=len(results),
        filters_applied=filters_applied if filters_applied else None,
    )


@router.post("/", response_model=schemas.AnimeSearchResponse)
async def search_anime_post(query: schemas.AnimeSearchQuery, ratings: RatingService = Depends(get_rating_service)):
    """
    Search anime (POST)
    """
    return await search_anime(
        q=query.q,
        source=query.source,
        year=query.year,
        month=query.month,
        studio=query.studio,
        director=query.director,
        source_type=query.source_type,
        match_mode=query.match_mode,
        extra_scores=query.extra_scores,
        debug_scores=query.debug_scores,
        limit=query.limit,
        offset=query.offset,
        anime_type=query.anime_type,
        include_scores=query.include_scores,
        ratings=ratings,
    )
