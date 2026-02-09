#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计信息 API
"""

from collections import Counter
from datetime import datetime

from fastapi import APIRouter

from web_api.api_v1 import schemas
from web_api.api_v1.deps import get_airing_list, get_subscribed_list

router = APIRouter()


@router.get("/", response_model=schemas.StatsInfo)
async def get_stats():
    """
    获取统计信息
    
    返回动漫数据的统计概况
    """
    airing_data = get_airing_list()
    subscribed_data = get_subscribed_list()
    
    # 基础统计
    total_airing = len([k for k in airing_data.keys() if k != "total"])
    total_subscribed = len([k for k in subscribed_data.keys() if k != "total"])
    
    # 评分分布
    score_dist = Counter()
    studio_dist = Counter()
    year_dist = Counter()
    
    # 统计正在放送的
    for name, info in airing_data.items():
        if name == "total" or not isinstance(info, dict):
            continue
        
        # 评分分布
        score = info.get("score")
        if score:
            score_range = f"{int(score)}-{int(score)+1}"
            score_dist[score_range] += 1
        
        # 年份分布
        time_info = info.get("time", {})
        year = time_info.get("year")
        if year:
            year_dist[str(year)] += 1
    
    # 获取最后更新时间
    last_updated = None
    # TODO: 从文件修改时间获取
    
    return schemas.StatsInfo(
        total_anime=total_airing + total_subscribed,
        airing_count=total_airing,
        subscribed_count=total_subscribed,
        score_distribution=dict(score_dist),
        year_distribution=dict(year_dist),
        last_updated=last_updated,
    )


@router.get("/score-distribution")
async def get_score_distribution():
    """
    获取评分分布
    
    返回各分数段的动漫数量
    """
    data = get_airing_list()
    
    distribution = Counter()
    for name, info in data.items():
        if name == "total" or not isinstance(info, dict):
            continue
        
        score = info.get("score")
        if score:
            # 按 0.5 分段
            bucket = round(score * 2) / 2
            distribution[bucket] += 1
    
    return {
        "distribution": dict(sorted(distribution.items())),
        "total": sum(distribution.values()),
    }


@router.get("/studio-ranking")
async def get_studio_ranking(limit: int = 10):
    """
    获取制作公司排名
    
    返回动漫数量最多的制作公司
    """
    data = get_airing_list()
    
    studio_scores = {}
    studio_counts = Counter()
    
    for name, info in data.items():
        if name == "total" or not isinstance(info, dict):
            continue
        
        studio = info.get("studio")
        if studio:
            studio_counts[studio] += 1
            
            # 计算平均分
            score = info.get("score") or 0
            if studio not in studio_scores:
                studio_scores[studio] = []
            studio_scores[studio].append(score)
    
    # 计算平均评分
    studio_avg_scores = {
        studio: sum(scores) / len(scores)
        for studio, scores in studio_scores.items()
        if len(scores) >= 1
    }
    
    # 按数量排序
    top_studios = studio_counts.most_common(limit)
    
    return {
        "by_count": [
            {
                "studio": studio,
                "count": count,
                "avg_score": round(studio_avg_scores.get(studio, 0), 2),
            }
            for studio, count in top_studios
        ],
    }
