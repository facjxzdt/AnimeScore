#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnimeScore API v1

RESTful API 设计规范：
- 版本前缀: /api/v1
- 标准 HTTP 状态码
- 统一响应格式
- 资源导向的 URL 设计
"""

from .router import api_router

__all__ = ["api_router"]
