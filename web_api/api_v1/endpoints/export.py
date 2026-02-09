#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出 API

提供数据导出功能
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from data.config import work_dir

router = APIRouter()


@router.get("/csv")
async def export_csv(
    type: str = Query("airing", description="导出类型: airing, subscribed"),
):
    """
    导出 CSV 文件
    
    - **type**: 导出类型
      - `airing`: 正在放送的动漫
      - `subscribed`: 订阅的动漫
    """
    if type == "airing":
        filename = work_dir + "/data/score.csv"
        download_name = "airing_anime.csv"
    elif type == "subscribed":
        filename = work_dir + "/data/sub_score.csv"
        download_name = "subscribed_anime.csv"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid type: {type}")
    
    import os
    if not os.path.exists(filename):
        raise HTTPException(status_code=404, detail=f"CSV file not found: {type}")
    
    return FileResponse(
        filename,
        filename=download_name,
        media_type="text/csv",
    )


@router.get("/json")
async def export_json(
    type: str = Query("airing", description="导出类型: airing, subscribed"),
):
    """
    导出 JSON 文件
    
    - **type**: 导出类型
      - `airing`: 正在放送的动漫
      - `subscribed`: 订阅的动漫
    """
    import json
    
    if type == "airing":
        filename = work_dir + "/data/jsons/score_sorted.json"
    elif type == "subscribed":
        filename = work_dir + "/data/jsons/sub_score_sorted.json"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid type: {type}")
    
    import os
    if not os.path.exists(filename):
        raise HTTPException(status_code=404, detail=f"JSON file not found: {type}")
    
    return FileResponse(
        filename,
        filename=f"{type}_anime.json",
        media_type="application/json",
    )
