#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API v1 数据模型 (Pydantic Schemas)
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== 基础响应模型 ====================

class APIResponse(BaseModel):
    """标准 API 响应"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error_code: str
    message: str
    details: Optional[Dict] = None


# ==================== 动漫信息模型 ====================

class AnimeIDs(BaseModel):
    """各平台 ID"""
    bgm_id: Optional[str] = None
    mal_id: Optional[str] = None
    anilist_id: Optional[str] = None
    anikore_id: Optional[str] = None
    filmarks_id: Optional[str] = None


class AnimeScores(BaseModel):
    """各平台评分"""
    bgm: Optional[float] = Field(None, description="Bangumi 评分")
    mal: Optional[float] = Field(None, description="MyAnimeList 评分")
    anilist: Optional[float] = Field(None, description="AniList 评分")
    anikore: Optional[float] = Field(None, description="Anikore 评分")
    filmarks: Optional[float] = Field(None, description="Filmarks 评分")
    total: Optional[float] = Field(None, description="综合评分")


class AnimeTime(BaseModel):
    """放送时间"""
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    weekday: Optional[int] = None


class AnimeInfo(BaseModel):
    """动漫详细信息"""
    name: str = Field(..., description="日文原名")
    name_cn: Optional[str] = Field(None, description="中文名")
    name_en: Optional[str] = Field(None, description="英文名")
    
    ids: AnimeIDs = Field(default_factory=AnimeIDs)
    scores: AnimeScores = Field(default_factory=AnimeScores)
    time: Optional[AnimeTime] = None
    
    poster: Optional[str] = Field(None, description="封面图片 URL")
    studio: Optional[str] = Field(None, description="制作公司")
    director: Optional[str] = Field(None, description="监督")
    source: Optional[str] = Field(None, description="原作类型")
    summary: Optional[str] = Field(None, description="简介")
    
    is_airing: Optional[bool] = Field(None, description="是否正在放送")
    is_subscribed: Optional[bool] = Field(None, description="是否已订阅")


class AnimeListResponse(BaseModel):
    """动漫列表响应"""
    items: List[AnimeInfo]
    total: int
    page: Optional[int] = 1
    page_size: Optional[int] = None


# ==================== 搜索相关模型 ====================

class SearchSource(str):
    """搜索源枚举"""
    PRECISE = "precise"    # 多源交叉验证搜索
    MEILI = "meili"        # MeiliSearch 本地搜索
    BANGUMI = "bangumi"    # Bangumi 搜索


class AnimeSearchQuery(BaseModel):
    """动漫搜索查询参数"""
    q: str = Field(..., description="搜索关键词", min_length=1)
    source: str = Field("precise", description="搜索源: precise, meili, bangumi")
    
    # 过滤条件
    year: Optional[int] = Field(None, description="年份过滤")
    month: Optional[int] = Field(None, description="月份过滤")
    studio: Optional[str] = Field(None, description="制作公司过滤")
    director: Optional[str] = Field(None, description="监督过滤")
    source_type: Optional[str] = Field(None, description="原作类型过滤", alias="source")
    
    # 分页
    limit: int = Field(10, ge=1, le=50, description="返回数量限制")
    offset: int = Field(0, ge=0, description="偏移量")
    
    class Config:
        populate_by_name = True


class AnimeSearchResult(AnimeInfo):
    """搜索结果（包含置信度）"""
    confidence: Optional[float] = Field(None, description="匹配置信度")
    matched_source: Optional[List[str]] = Field(None, description="匹配的搜索源")


class AnimeSearchResponse(BaseModel):
    """搜索响应"""
    query: str
    source: str
    results: List[AnimeSearchResult]
    total: int
    filters_applied: Optional[Dict] = None


# ==================== 季番相关模型 ====================

class SeasonInfo(BaseModel):
    """季番信息"""
    year: int
    season: str  # winter, spring, summer, fall
    name: str    # 如 "2024年1月冬番"


class AnimeSeasonResponse(BaseModel):
    """季番列表响应"""
    season: SeasonInfo
    anime_list: List[AnimeInfo]
    total: int
    updated_at: Optional[str] = None


# ==================== 导出相关模型 ====================

class ExportFormat(str):
    """导出格式"""
    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"


class ExportQuery(BaseModel):
    """导出查询参数"""
    type: str = Field("airing", description="类型: airing, subscribed, all")
    format: str = Field("csv", description="格式: csv, json, xlsx")


# ==================== 健康检查模型 ====================

class HealthStatus(BaseModel):
    """健康状态"""
    status: str  # ok, degraded, error
    version: str
    timestamp: str
    uptime: Optional[float] = None
    
    services: Optional[Dict[str, bool]] = None  # 各服务状态


# ==================== 统计信息模型 ====================

class StatsInfo(BaseModel):
    """统计信息"""
    total_anime: int
    airing_count: int
    subscribed_count: int
    
    score_distribution: Optional[Dict[str, int]] = None
    studio_distribution: Optional[Dict[str, int]] = None
    year_distribution: Optional[Dict[str, int]] = None
    
    last_updated: Optional[str] = None
