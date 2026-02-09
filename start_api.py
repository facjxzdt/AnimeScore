#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnimeScore API 启动脚本
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置环境变量
os.environ["PYTHONIOENCODING"] = "utf-8"

from web_api.main import app
import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("AnimeScore API Server")
    print("=" * 60)
    print("\nAPI 端点:")
    print("  - 文档: http://localhost:5001/docs")
    print("  - 健康检查: http://localhost:5001/api/v1/health/")
    print("  - 旧版 API: http://localhost:5001/air")
    print("  - 新版 API: http://localhost:5001/api/v1/anime/airing")
    print("\n按 Ctrl+C 停止服务\n")
    
    uvicorn.run(
        app="web_api.main:app",
        host="0.0.0.0",
        port=5001,
        reload=False,
        log_level="info",
    )
