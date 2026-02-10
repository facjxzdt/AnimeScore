#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnimeScore API 主入口 (仅保留 v1)
"""

import os
import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from web_api.api_v1 import api_router as api_v1_router

# ==================== FastAPI 应用配置 ====================

app = FastAPI(
    title="AnimeScore API",
    description="动漫评分聚合 API - 支持 Bangumi、MyAnimeList、AniList 等多平台评分",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== API v1 路由 ====================

app.include_router(
    api_v1_router,
    prefix="/api/v1",
    tags=["v1"],
)

# ==================== 根路由 ====================

@app.get("/")
async def root():
    """根路由"""
    return {"status": 200, "message": "AnimeScore API", "version": "1.0.0", "docs": "/docs"}

# ==================== 错误处理 ====================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_code": "INTERNAL_ERROR",
            "message": str(exc),
        }
    )

if __name__ == "__main__":
    # 启动服务
    uvicorn.run(
        app="web_api.main:app",
        host="0.0.0.0",
        port=5001,
        reload=False,
    )
