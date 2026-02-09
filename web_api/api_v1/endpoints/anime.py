#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动漫资源 API

提供动漫列表和单条动漫信息的获取
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from web_api.api_v1 import schemas
from web_api.api_v1.deps import (
    convert_single_anime,
    get_airing_list,
    get_subscribed_list,
    normalize_anime_data,
)

router = APIRouter()


@router.get("/airing", response_model=schemas.AnimeListResponse)
async def get_airing_anime(
    limit: Optional[int] = Query(None, ge=1, le=100, description="返回数量限制"),
    sort_by: str = Query("score", description="排序字段: score, name, time"),
):
    """
    获取正在放送的动漫列表
    
    返回当前季度正在放送的动漫及其评分信息
    """
    data = get_airing_list()
    
    if not data or not isinstance(data, dict):
        raise HTTPException(status_code=404, detail="No airing anime data available")
    
    # 转换为列表
    items = []
    for name, info in data.items():
        if name == "total" or not isinstance(info, dict):
            continue
        
        anime_data = convert_single_anime(name, info)
        anime_data["is_airing"] = True
        items.append(schemas.AnimeInfo(**anime_data))
    
    # 排序
    if sort_by == "score":
        items.sort(key=lambda x: (x.scores.total or 0), reverse=True)
    elif sort_by == "name":
        items.sort(key=lambda x: x.name)
    
    # 分页
    total = len(items)
    if limit:
        items = items[:limit]
    
    return schemas.AnimeListResponse(
        items=items,
        total=total,
        page=1,
        page_size=limit or total,
    )


@router.get("/subscribed", response_model=schemas.AnimeListResponse)
async def get_subscribed_anime(
    limit: Optional[int] = Query(None, ge=1, le=100, description="返回数量限制"),
    sort_by: str = Query("score", description="排序字段"),
):
    """
    获取订阅的动漫列表
    
    返回用户订阅的动漫及其评分信息
    """
    data = get_subscribed_list()
    
    if not data or not isinstance(data, dict):
        raise HTTPException(status_code=404, detail="No subscribed anime data available")
    
    items = []
    for name, info in data.items():
        if name == "total" or not isinstance(info, dict):
            continue
        
        anime_data = convert_single_anime(name, info)
        anime_data["is_subscribed"] = True
        items.append(schemas.AnimeInfo(**anime_data))
    
    # 排序
    if sort_by == "score":
        items.sort(key=lambda x: (x.scores.total or 0), reverse=True)
    elif sort_by == "name":
        items.sort(key=lambda x: x.name)
    
    total = len(items)
    if limit:
        items = items[:limit]
    
    return schemas.AnimeListResponse(
        items=items,
        total=total,
        page=1,
        page_size=limit or total,
    )


@router.get("/season/current", response_model=schemas.AnimeSeasonResponse)
async def get_current_season():
    """
    获取当前季番
    
    返回当前季度的动漫列表
    """
    data = get_airing_list()
    
    if not data:
        raise HTTPException(status_code=404, detail="No season data available")
    
    # 构建季番信息
    # 从数据中提取年份和季节
    first_anime = None
    for name, info in data.items():
        if isinstance(info, dict) and name != "total":
            first_anime = info
            break
    
    year = 2024
    season_name = "winter"
    
    if first_anime and "time" in first_anime:
        time_info = first_anime["time"]
        year = time_info.get("year", 2024)
        month = time_info.get("month", 1)
        
        # 判断季节
        if month in [12, 1, 2]:
            season_name = "winter"
        elif month in [3, 4, 5]:
            season_name = "spring"
        elif month in [6, 7, 8]:
            season_name = "summer"
        else:
            season_name = "fall"
    
    season_info = schemas.SeasonInfo(
        year=year,
        season=season_name,
        name=f"{year}年{month if first_anime else 1}月{get_season_cn_name(season_name)}番",
    )
    
    # 转换动漫列表
    anime_list = []
    for name, info in data.items():
        if name == "total" or not isinstance(info, dict):
            continue
        anime_data = convert_single_anime(name, info)
        anime_list.append(schemas.AnimeInfo(**anime_data))
    
    anime_list.sort(key=lambda x: (x.scores.total or 0), reverse=True)
    
    return schemas.AnimeSeasonResponse(
        season=season_info,
        anime_list=anime_list,
        total=len(anime_list),
    )


@router.get("/{bgm_id}", response_model=schemas.AnimeInfo)
async def get_anime_by_id(
    bgm_id: str = Path(..., description="Bangumi ID"),
):
    """
    根据 Bangumi ID 获取动漫详情
    
    - **bgm_id**: Bangumi 动漫 ID
    """
    # 先从正在放送列表查找
    data = get_airing_list()
    
    for name, info in data.items():
        if not isinstance(info, dict):
            continue
        if str(info.get("bgm_id")) == str(bgm_id):
            anime_data = convert_single_anime(name, info)
            anime_data["is_airing"] = True
            return schemas.AnimeInfo(**anime_data)
    
    # 再从订阅列表查找
    data = get_subscribed_list()
    
    for name, info in data.items():
        if not isinstance(info, dict):
            continue
        if str(info.get("bgm_id")) == str(bgm_id):
            anime_data = convert_single_anime(name, info)
            anime_data["is_subscribed"] = True
            return schemas.AnimeInfo(**anime_data)
    
    # 如果都没找到，尝试从 Bangumi API 获取
    # TODO: 实现从 API 获取
    raise HTTPException(status_code=404, detail=f"Anime with bgm_id {bgm_id} not found")


def get_season_cn_name(season: str) -> str:
    """获取季节中文名"""
    season_map = {
        "winter": "冬",
        "spring": "春",
        "summer": "夏",
        "fall": "秋",
    }
    return season_map.get(season, "")
