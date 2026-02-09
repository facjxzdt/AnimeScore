#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnimeScore API 主入口

提供 API v1 和旧版 API 的兼容支持
"""

import json
import sys
import threading
import time
from typing import Optional

import schedule
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from data.config import work_dir
from web_api.api_v1 import api_router as api_v1_router

# 尝试导入旧版模块
# 如果导入失败，API 仍然可以运行但旧版端点不可用
OLD_API_AVAILABLE = False
try:
    import web_api.meili_search
    from apis.precise import search_anime_precise
    from deamon import meili_update, updata_score
    from web_api.wrapper import AnimeScore
    
    ans = AnimeScore()
    OLD_API_AVAILABLE = True
    print("[INFO] Legacy API modules loaded successfully")
except ImportError as e:
    print(f"[WARN] Failed to load legacy API modules: {e}")
    print("[WARN] Legacy API endpoints will not be available")
    ans = None

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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== API v1 路由 ====================

app.include_router(
    api_v1_router,
    prefix="/api/v1",
    tags=["v1"],
)

# ==================== 旧版 API (兼容) ====================

if OLD_API_AVAILABLE:
    
    def get_list(method):
        """获取列表数据（旧版）"""
        if method == "sub":
            file_path = work_dir + "/data/jsons/sub_score_sorted.json"
        else:
            file_path = work_dir + "/data/jsons/score_sorted.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @app.get("/")
    async def root():
        """根路由（旧版）"""
        return {"status": 200, "message": "AnimeScore API", "version": "1.0.0", "docs": "/docs"}

    @app.get("/air")
    async def air():
        """获取正在放送的动漫列表（旧版）"""
        lists = get_list(method="air")
        return {"status": 200, "body": lists}

    @app.get("/sub")
    def sub():
        """获取订阅的动漫列表（旧版）"""
        lists = get_list(method="sub")
        return {"status": 200, "body": lists}

    @app.get("/search/{bgm_id}")
    def search(bgm_id: str):
        """根据 Bangumi ID 搜索（旧版）"""
        try:
            result = ans.search_bgm_id(bgm_id)
            return {"status": 200, "body": result}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"status": 500, "error": str(e)}
            )

    @app.get("/search/meili/{string}")
    def search_meili(string: str):
        """MeiliSearch 搜索（旧版）"""
        try:
            result = ans.search_anime_name(string)
            return {"status": 200, "body": result}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"status": 500, "error": str(e)}
            )

    @app.get("/search/precise/{keyword}")
    def search_precise(
        keyword: str,
        year: Optional[int] = None,
        month: Optional[int] = None,
        studio: Optional[str] = None,
        director: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 10,
    ):
        """
        多源交叉验证精确搜索（旧版）
        
        推荐使用新 API: GET /api/v1/search?q={keyword}
        """
        try:
            results = search_anime_precise(
                keyword=keyword,
                year=year,
                month=month,
                studio=studio,
                director=director,
                source=source,
                top_n=limit,
            )
            return {"status": 200, "body": results}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"status": 500, "error": str(e)}
            )

    @app.get("/csv/{method}")
    def get_csv(method: str):
        """下载 CSV（旧版）"""
        from fastapi.responses import FileResponse
        
        if method == "air":
            filename = work_dir + "/data/score.csv"
        else:
            filename = work_dir + "/data/sub_score.csv"
        
        import os
        if not os.path.exists(filename):
            return JSONResponse(
                status_code=404,
                content={"status": 404, "error": "File not found"}
            )
        
        return FileResponse(
            filename,
            filename="score.csv",
        )

else:
    @app.get("/")
    async def root():
        """根路由"""
        return {
            "status": 200,
            "message": "AnimeScore API",
            "version": "1.0.0",
            "docs": "/docs",
            "note": "Legacy API not available due to missing dependencies"
        }

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

# ==================== 后台任务 ====================

def deamon(interval=1):
    """后台定时任务"""
    cease_continuous_run = threading.Event()

    class ScheduleThread(threading.Thread):
        @classmethod
        def run(cls):
            while not cease_continuous_run.is_set():
                schedule.run_pending()
                time.sleep(interval)

    continuous_thread = ScheduleThread()
    continuous_thread.start()
    return cease_continuous_run

# ==================== 启动入口 ====================

if __name__ == "__main__":
    # 初始化
    if OLD_API_AVAILABLE and ans:
        try:
            ans.init()
            # 设置定时任务
            schedule.every().day.at("19:30").do(updata_score)
            schedule.every().day.at("19:30").do(meili_update)
            _deamon = deamon()
            print("[INFO] Background scheduler started")
        except Exception as e:
            print(f"[WARN] Failed to initialize legacy components: {e}")
    
    # 启动服务
    uvicorn.run(
        app="main:app",
        host="0.0.0.0",
        port=5001,
        reload=False,
    )
