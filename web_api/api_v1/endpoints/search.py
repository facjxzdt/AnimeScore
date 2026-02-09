#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搜索相关 API

提供多种搜索方式：
- precise: 多源交叉验证搜索
- meili: MeiliSearch 本地搜索
- bangumi: Bangumi 搜索
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from apis.precise import search_anime_precise
from web_api.api_v1 import schemas
from web_api.api_v1.deps import get_anime_score
from web_api.wrapper import AnimeScore

router = APIRouter()


@router.get("/", response_model=schemas.AnimeSearchResponse)
async def search_anime(
    q: str = Query(..., description="搜索关键词", min_length=1),
    source: str = Query("precise", description="搜索源: precise, meili, bangumi"),
    year: Optional[int] = Query(None, description="年份过滤"),
    month: Optional[int] = Query(None, description="月份过滤"),
    studio: Optional[str] = Query(None, description="制作公司过滤"),
    director: Optional[str] = Query(None, description="监督过滤"),
    source_type: Optional[str] = Query(None, description="原作类型过滤"),
    limit: int = Query(10, ge=1, le=50, description="返回数量限制"),
    ans: AnimeScore = Depends(get_anime_score),
):
    """
    搜索动漫
    
    支持多种搜索源：
    - **precise**: 多源交叉验证搜索（推荐）
    - **meili**: MeiliSearch 本地搜索
    - **bangumi**: Bangumi API 搜索
    
    示例:
    - `/api/v1/search?q=葬送的芙莉莲`
    - `/api/v1/search?q=Frieren&year=2023&source=precise`
    """
    filters_applied = {}
    results = []
    
    try:
        if source == "precise":
            # 多源交叉验证搜索
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
            
            # 转换为标准格式
            for item in precise_results:
                result = schemas.AnimeSearchResult(
                    name=item.get("name", ""),
                    name_cn=item.get("name_cn"),
                    name_jp=item.get("name_jp"),
                    ids=schemas.AnimeIDs(
                        bgm_id=item.get("bgm_id"),
                        mal_id=item.get("mal_id"),
                        anilist_id=item.get("anilist_id"),
                    ),
                    scores=schemas.AnimeScores(
                        bgm=item.get("bgm_score"),
                        mal=item.get("mal_score"),
                        anilist=item.get("anilist_score"),
                    ),
                    year=item.get("year"),
                    month=item.get("month"),
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
        
        elif source == "meili":
            # MeiliSearch 本地搜索
            meili_results = ans.search_anime_name(q)
            
            # 处理结果...
            if isinstance(meili_results, dict) and "hits" in meili_results:
                for item in meili_results["hits"][:limit]:
                    # 转换格式
                    result = schemas.AnimeSearchResult(
                        name=item.get("name", ""),
                        name_cn=item.get("name_cn"),
                        ids=schemas.AnimeIDs(bgm_id=str(item.get("bgm_id"))),
                        scores=schemas.AnimeScores(
                            bgm=item.get("bgm_score"),
                            total=item.get("score"),
                        ),
                        poster=item.get("poster"),
                        confidence=1.0 if item.get("name") == q else 0.5,
                        matched_source=["meili"],
                    )
                    results.append(result)
        
        elif source == "bangumi":
            # Bangumi 搜索
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
    搜索动漫 (POST 方式)
    
    适合复杂的搜索条件
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
