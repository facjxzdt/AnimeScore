#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API v1 依赖注入
"""

import json
import os
from functools import lru_cache
from typing import Generator, Optional

from data.config import work_dir
from web_api.wrapper import AnimeScore


# ==================== 依赖函数 ====================

def get_anime_score() -> Generator[AnimeScore, None, None]:
    """
    获取 AnimeScore 实例
    
    Yields:
        AnimeScore 实例
    """
    ans = AnimeScore()
    try:
        yield ans
    finally:
        pass  # 清理操作（如果需要）


@lru_cache()
def get_airing_list() -> dict:
    """
    获取正在放送列表（带缓存）
    
    Returns:
        正在放送的动漫列表
    """
    try:
        with open(work_dir + "/data/jsons/score_sorted.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@lru_cache()
def get_subscribed_list() -> dict:
    """
    获取订阅列表（带缓存）
    
    Returns:
        订阅的动漫列表
    """
    try:
        with open(work_dir + "/data/jsons/sub_score_sorted.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def clear_cache():
    """清除缓存"""
    get_airing_list.cache_clear()
    get_subscribed_list.cache_clear()


# ==================== 辅助函数 ====================

def normalize_anime_data(data: dict) -> dict:
    """
    将旧版数据格式转换为新版格式
    
    Args:
        data: 旧版动漫数据
        
    Returns:
        新版格式的数据
    """
    if not isinstance(data, dict):
        return {}
    
    # 处理列表格式（旧版是 dict，key 是动漫名）
    if "name" not in data and len(data) > 0:
        # 取第一个作为示例转换
        first_key = list(data.keys())[0]
        if isinstance(data[first_key], dict):
            return {
                "items": [
                    convert_single_anime(name, info)
                    for name, info in data.items()
                    if isinstance(info, dict) and name != "total"
                ],
                "total": data.get("total", len(data) - 1 if "total" in data else len(data))
            }
    
    return convert_single_anime(data.get("name", ""), data)


def convert_single_anime(name: str, info: dict) -> dict:
    """
    转换单个动漫数据格式
    
    Args:
        name: 动漫名称
        info: 动漫信息
        
    Returns:
        新版格式的数据
    """
    if not isinstance(info, dict):
        return {"name": name}
    
    # IDs
    ids = info.get("ids", {})
    
    # Scores
    scores = {
        "bgm": info.get("bgm_score"),
        "mal": info.get("mal_score"),
        "anilist": info.get("anl_score"),
        "anikore": info.get("ank_score"),
        "filmarks": info.get("fm_score"),
        "total": info.get("score"),
    }
    
    # Time
    time_info = info.get("time", {})
    time_obj = None
    if time_info:
        time_obj = {
            "year": time_info.get("year"),
            "month": time_info.get("month"),
            "day": time_info.get("day"),
        }
    
    return {
        "name": info.get("name", name),
        "name_cn": info.get("name_cn"),
        "name_en": info.get("name_en"),
        "ids": {
            "bgm_id": info.get("bgm_id") or ids.get("bgm_id"),
            "mal_id": ids.get("mal_id"),
            "anilist_id": ids.get("anl_id"),
            "anikore_id": ids.get("ank_id"),
            "filmarks_id": ids.get("fm_id"),
        },
        "scores": {k: v for k, v in scores.items() if v is not None},
        "time": time_obj,
        "poster": info.get("poster"),
        "studio": info.get("studio"),
        "director": info.get("director"),
        "source": info.get("source"),
        "summary": info.get("summary"),
    }
