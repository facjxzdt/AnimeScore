#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API模块
提供各类动漫数据源的API客户端
"""

from .bangumi import Bangumi
from .anilist import AniList
from .mal import MyAnimeList as MAL
from .anikore import Anikore
from .filmarks import Filmarks
from .precise import (
    AnimeInfo,
    BangumiSearcher,
    AniListSearcher,
    JikanSearcher,
    CrossValidator,
    search_anime_precise,
)

__all__ = [
    # 原有API
    "Bangumi",
    "AniList",
    "MAL",
    "Anikore",
    "Filmarks",
    # 精确搜索API
    "AnimeInfo",
    "BangumiSearcher",
    "AniListSearcher",
    "JikanSearcher",
    "CrossValidator",
    "search_anime_precise",
]
