#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search APIs
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from apis.precise import search_anime_precise
from web_api.api_v1 import schemas
from web_api.api_v1.deps import get_anime_score
from web_api.wrapper import AnimeScore

router = APIRouter()


@router.get("/", response_model=schemas.AnimeSearchResponse)
async def search_anime(
    q: str = Query(..., min_length=1, description="Search keyword"),
    source: str = Query("precise", description="Search source: precise, bangumi"),
    year: Optional[int] = Query(None, description="Year filter"),
    month: Optional[int] = Query(None, description="Month filter"),
    studio: Optional[str] = Query(None, description="Studio filter"),
    director: Optional[str] = Query(None, description="Director filter"),
    source_type: Optional[str] = Query(None, description="Source type filter"),
    limit: int = Query(10, ge=1, le=50, description="Limit"),
    ans: AnimeScore = Depends(get_anime_score),
):
    """
    Search anime by keyword.
    """
    filters_applied = {}
    results = []

    try:
        if source == "precise":
            filters = {
                "year": year,
                "month": month,
                "studio": studio,
                "director": director,
                "source": source_type,
            }
            filters = {k: v for k, v in filters.items() if v is not None}
            filters_applied = filters

            precise_results = search_anime_precise(q, **filters, top_n=limit)

            for item in precise_results:
                result = schemas.AnimeSearchResult(
                    name=item.get("name", ""),
                    name_cn=item.get("name_cn"),
                    name_en=item.get("name_en"),
                    ids=schemas.AnimeIDs(
                        bgm_id=item.get("bgm_id"),
                        mal_id=item.get("mal_id"),
                        anilist_id=item.get("anilist_id"),
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
                )
                results.append(result)

        elif source == "bangumi":
            bgm_results = ans.Bangumi().search_anime(q)

            if isinstance(bgm_results, dict) and "data" in bgm_results:
                for item in bgm_results["data"][:limit]:
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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return schemas.AnimeSearchResponse(
        query=q,
        source=source,
        results=results,
        total=len(results),
        filters_applied=filters_applied if filters_applied else None,
    )


@router.post("/", response_model=schemas.AnimeSearchResponse)
async def search_anime_post(query: schemas.AnimeSearchQuery):
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
        limit=query.limit,
    )
