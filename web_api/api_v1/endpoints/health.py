#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康检查 API
"""

import time
from datetime import datetime

from fastapi import APIRouter

from web_api.api_v1 import schemas

router = APIRouter()

# 启动时间
START_TIME = time.time()


@router.get("/", response_model=schemas.HealthStatus)
async def health_check():
    """
    健康检查
    
    返回 API 运行状态和各服务健康状况
    """
    uptime = time.time() - START_TIME
    
    # 检查各服务状态
    services = {
        "api": True,
        "data_files": check_data_files(),
        "meilisearch": check_meilisearch(),
    }
    
    # 判断整体状态
    if all(services.values()):
        status = "ok"
    elif services["api"]:
        status = "degraded"
    else:
        status = "error"
    
    return schemas.HealthStatus(
        status=status,
        version="1.0.0",
        timestamp=datetime.now().isoformat(),
        uptime=uptime,
        services=services,
    )


@router.get("/ping")
async def ping():
    """
    简单的 ping 检查
    
    用于快速检测服务是否存活
    """
    return {"message": "pong"}


def check_data_files() -> bool:
    """检查数据文件是否存在"""
    try:
        from data.config import work_dir
        import os
        
        required_files = [
            work_dir + "/data/jsons/score_sorted.json",
            work_dir + "/data/jsons/animes.json",
        ]
        
        for f in required_files:
            if not os.path.exists(f):
                return False
        return True
    except Exception:
        return False


def check_meilisearch() -> bool:
    """检查 MeiliSearch 是否可用"""
    try:
        # 尝试导入和连接
        from web_api.meili_search import Meilisearch
        meili = Meilisearch()
        # 这里可以添加实际的连接测试
        return True
    except Exception:
        return False
