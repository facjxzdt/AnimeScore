#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API v1 路由聚合
"""

from fastapi import APIRouter

from web_api.api_v1.endpoints import anime, export, health, search, stats

# 创建主路由
api_router = APIRouter()

# 注册各模块路由
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"],
)

api_router.include_router(
    anime.router,
    prefix="/anime",
    tags=["anime"],
)

api_router.include_router(
    search.router,
    prefix="/search",
    tags=["search"],
)

api_router.include_router(
    export.router,
    prefix="/export",
    tags=["export"],
)

api_router.include_router(
    stats.router,
    prefix="/stats",
    tags=["stats"],
)
