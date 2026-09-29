#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康检查 API
"""

import time
from datetime import datetime

from fastapi import APIRouter

from web_api.api_v1 import schemas
from services.catalog import get_repository

router = APIRouter()

# 启动时间
START_TIME = time.time()


@router.get("/", response_model=schemas.HealthStatus)
def health_check():
    """
    健康检查
    
    返回 API 运行状态和各服务健康状况
    """
    uptime = time.time() - START_TIME
    
    # 检查各服务状态
    catalog = get_repository().status()
    services = {
        "api": True,
        "data_files": catalog["available"],
        "bangumi_data": catalog["available"],
        "catalog_fresh": catalog["available"] and not catalog["stale"] and not catalog["last_error"],
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
    return get_repository().status()["available"]
