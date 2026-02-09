#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API v1 data models (Pydantic schemas)
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== Base responses ====================

class APIResponse(BaseModel):
    """Standard API response"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """Error response"""
    success: bool = False
    error_code: str
    message: str
    details: Optional[Dict] = None


# ==================== Anime models ====================

class AnimeIDs(BaseModel):
    """IDs from platforms"""
    bgm_id: Optional[str] = None
    mal_id: Optional[str] = None
    anilist_id: Optional[str] = None
    anikore_id: Optional[str] = None
    filmarks_id: Optional[str] = None
    douban_id: Optional[str] = None
    bili_id: Optional[str] = None
    anidb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    wikidata_id: Optional[str] = None


class AnimeScores(BaseModel):
    """Scores from platforms"""
    bgm: Optional[float] = Field(None, description="Bangumi score")
    mal: Optional[float] = Field(None, description="MyAnimeList score")
    anilist: Optional[float] = Field(None, description="AniList score")
    anikore: Optional[float] = Field(None, description="Anikore score")
    filmarks: Optional[float] = Field(None, description="Filmarks score")
    total: Optional[float] = Field(None, description="Aggregated score")


class AnimeTime(BaseModel):
    """Airing time"""
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    weekday: Optional[int] = None


class AnimeInfo(BaseModel):
    """Anime details"""
    name: str = Field(..., description="Japanese title")
    name_cn: Optional[str] = Field(None, description="Chinese title")
    name_en: Optional[str] = Field(None, description="English title")

    ids: AnimeIDs = Field(default_factory=AnimeIDs)
    scores: AnimeScores = Field(default_factory=AnimeScores)
    time: Optional[AnimeTime] = None

    poster: Optional[str] = Field(None, description="Poster URL")
    studio: Optional[str] = Field(None, description="Studio")
    director: Optional[str] = Field(None, description="Director")
    source: Optional[str] = Field(None, description="Source type")
    summary: Optional[str] = Field(None, description="Summary")

    is_airing: Optional[bool] = Field(None, description="Is airing")
    is_subscribed: Optional[bool] = Field(None, description="Is subscribed")


class AnimeListResponse(BaseModel):
    """Anime list response"""
    items: List[AnimeInfo]
    total: int
    page: Optional[int] = 1
    page_size: Optional[int] = None


# ==================== Search models ====================

class SearchSource(str):
    """Search source"""
    PRECISE = "precise"
    BANGUMI = "bangumi"


class AnimeSearchQuery(BaseModel):
    """Anime search parameters"""
    q: str = Field(..., min_length=1, description="Search keyword")
    source: str = Field("precise", description="Search source: precise, bangumi")

    year: Optional[int] = Field(None, description="Year filter")
    month: Optional[int] = Field(None, description="Month filter")
    studio: Optional[str] = Field(None, description="Studio filter")
    director: Optional[str] = Field(None, description="Director filter")
    source_type: Optional[str] = Field(None, description="Source type filter", alias="source")

    limit: int = Field(10, ge=1, le=50, description="Limit")
    offset: int = Field(0, ge=0, description="Offset")

    class Config:
        populate_by_name = True


class AnimeSearchResult(AnimeInfo):
    """Search result with confidence"""
    confidence: Optional[float] = Field(None, description="Match confidence")
    matched_source: Optional[List[str]] = Field(None, description="Matched sources")


class AnimeSearchResponse(BaseModel):
    """Search response"""
    query: str
    source: str
    results: List[AnimeSearchResult]
    total: int
    filters_applied: Optional[Dict] = None


# ==================== Season models ====================

class SeasonInfo(BaseModel):
    """Season info"""
    year: int
    season: str  # winter, spring, summer, fall
    name: str    # e.g. "2024 winter"


class AnimeSeasonResponse(BaseModel):
    """Season response"""
    season: SeasonInfo
    anime_list: List[AnimeInfo]
    total: int
    updated_at: Optional[str] = None


# ==================== Export models ====================

class ExportFormat(str):
    """Export format"""
    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"


class ExportQuery(BaseModel):
    """Export query parameters"""
    type: str = Field("airing", description="Type: airing, subscribed, all")
    format: str = Field("csv", description="Format: csv, json, xlsx")


# ==================== Health models ====================

class HealthStatus(BaseModel):
    """Health status"""
    status: str  # ok, degraded, error
    version: str
    timestamp: str
    uptime: Optional[float] = None

    services: Optional[Dict[str, bool]] = None


# ==================== Stats models ====================

class StatsInfo(BaseModel):
    """Stats info"""
    total_anime: int
    airing_count: int
    subscribed_count: int

    score_distribution: Optional[Dict[str, int]] = None
    studio_distribution: Optional[Dict[str, int]] = None
    year_distribution: Optional[Dict[str, int]] = None

    last_updated: Optional[str] = None
