#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnimeScore API 主入口 (仅保留 v1)
"""

import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
load_dotenv(Path(PROJECT_ROOT) / ".env", override=False)

from fastapi.concurrency import run_in_threadpool
from services.catalog import CatalogUnavailable, get_repository
from services.ratings import RatingService
from services.collector import Collector
from services.filmarks_mapping import FilmarksMapper
from services.filmarks_jobs import FilmarksJobs
from services.auth import AuthStore, OAuthLogFilter
from services.contributions import Contributions
from web_api.api_v1.deps import get_score_cache
from web_api.api_v1 import api_router as api_v1_router

# ==================== FastAPI 应用配置 ====================

logger = logging.getLogger(__name__)
logging.getLogger("uvicorn.access").addFilter(OAuthLogFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository = get_repository()
    auto_update = os.getenv("BANGUMI_DATA_AUTO_UPDATE", "1").lower() in {"1", "true", "yes", "on"}
    if auto_update:
        _, message = await run_in_threadpool(repository.refresh)
        logger.info(message)

    async def refresh_catalog():
        while True:
            await asyncio.sleep(3600)
            _, message = await run_in_threadpool(repository.refresh)
            logger.info(message)

    async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                 headers={"User-Agent": "facjxzdt/AnimeScore (https://github.com/facjxzdt/AnimeScore)"}) as client:
        app.state.ratings = RatingService(get_score_cache(), client)
        app.state.collector = Collector(repository, app.state.ratings)
        app.state.filmarks_mapper = FilmarksMapper(repository, app.state.ratings)
        app.state.filmarks_jobs = FilmarksJobs(app.state.filmarks_mapper)
        app.state.auth = AuthStore(get_score_cache())
        app.state.contributions = Contributions(repository, app.state.ratings)
        task = asyncio.create_task(refresh_catalog()) if auto_update else None
        collection_task = asyncio.create_task(app.state.collector.run())
        mapping_task = asyncio.create_task(app.state.filmarks_jobs.run())
        contribution_task = asyncio.create_task(app.state.contributions.run())
        try:
            yield
        finally:
            contribution_task.cancel()
            with suppress(asyncio.CancelledError):
                await contribution_task
            mapping_task.cancel()
            with suppress(asyncio.CancelledError):
                await mapping_task
            collection_task.cancel()
            with suppress(asyncio.CancelledError):
                await collection_task
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


app = FastAPI(
    title="AnimeScore API",
    description="基于 bangumi-data 的番剧目录与多平台评分聚合 API。基础数据：bangumi-data，CC BY 4.0。",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
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

FRONTEND = Path(PROJECT_ROOT) / "frontend/dist"
app.mount("/assets", StaticFiles(directory=str(FRONTEND), check_dir=False), name="frontend")


# ==================== 根路由 ====================

@app.get("/")
async def root():
    if not (FRONTEND / "index.html").exists():
        return JSONResponse(status_code=503, content={"detail": "Build the web app with: cd frontend && npm ci && npm run build"})
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/admin")
async def admin_page():
    if not (FRONTEND / "admin.html").exists():
        return JSONResponse(status_code=503, content={"detail": "Build the frontend first"})
    return FileResponse(FRONTEND / "admin.html", headers={"Cache-Control": "no-store"})

# ==================== 错误处理 ====================

@app.exception_handler(CatalogUnavailable)
async def catalog_unavailable_handler(request: Request, exc: CatalogUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})

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
    workers = max(1, int(os.getenv("API_WORKERS", "1")))
    uvicorn.run(
        app="web_api.main:app",
        host="0.0.0.0",
        port=5001,
        reload=False,
        workers=workers,
    )
