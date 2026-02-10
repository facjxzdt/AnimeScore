# AnimeScore API v1 文档

## 概述

API v1 采用 RESTful 设计，统一前缀为 `/api/v1`。

- 基础 URL: `/api/v1`
- 认证: 无
- 返回格式: 直接返回 JSON（无统一 `success` 包装）

## 端点总览

- 健康检查: `GET /api/v1/health/`, `GET /api/v1/health/ping`
- 动漫列表: `GET /api/v1/anime/airing`, `GET /api/v1/anime/subscribed`, `GET /api/v1/anime/season/current`, `GET /api/v1/anime/{bgm_id}`
- 搜索: `GET /api/v1/search/`, `POST /api/v1/search/`
- 导出: `GET /api/v1/export/csv`, `GET /api/v1/export/json`
- 统计: `GET /api/v1/stats/`, `GET /api/v1/stats/score-distribution`, `GET /api/v1/stats/studio-ranking`

---

## 健康检查

### GET /api/v1/health/
返回 API 运行状态。

**响应示例**:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2026-02-10T10:30:00",
  "uptime": 3600.5,
  "services": {
    "api": true,
    "data_files": true
  }
}
```

### GET /api/v1/health/ping
快速存活检查。

**响应示例**:
```json
{ "message": "pong" }
```

---

## 动漫列表

### GET /api/v1/anime/airing
获取正在放送列表。

**查询参数**:
- `limit` (int, optional): 返回数量限制 (1-100)
- `sort_by` (str, optional): 排序字段 `score` | `name` | `time`（默认 `score`）

**响应示例**:
```json
{
  "items": [
    {
      "name": "葬送のフリーレン",
      "name_cn": "葬送的芙莉莲",
      "ids": {
        "bgm_id": "400602",
        "mal_id": "52991",
        "anilist_id": "154587"
      },
      "scores": {
        "bgm": 8.6,
        "mal": 9.28,
        "anilist": 9.1,
        "total": 8.95
      },
      "poster": "https://...",
      "studio": "MADHOUSE",
      "is_airing": true
    }
  ],
  "total": 50,
  "page": 1,
  "page_size": 50
}
```

### GET /api/v1/anime/subscribed
获取订阅列表。

**查询参数**:
- `limit` (int, optional): 返回数量限制 (1-100)
- `sort_by` (str, optional): 排序字段 `score` | `name` | `time`

### GET /api/v1/anime/season/current
获取当前季番信息与列表。

**响应示例**:
```json
{
  "season": {
    "year": 2024,
    "season": "winter",
    "name": "2024 winter"
  },
  "anime_list": [ ... ],
  "total": 50
}
```

### GET /api/v1/anime/{bgm_id}
根据 Bangumi ID 获取动漫详情。

**路径参数**:
- `bgm_id` (str, required): Bangumi 动漫 ID

---

## 搜索

### GET /api/v1/search/
搜索动漫。`source=precise` 时使用 `apis/precise.py` 的多源交叉验证。

**查询参数**:
- `q` (str, required): 搜索关键词
- `source` (str, optional): `precise` | `bangumi`（默认 `precise`）
- `year` (int, optional): 年份过滤
- `month` (int, optional): 月份过滤
- `studio` (str, optional): 制作公司过滤
- `director` (str, optional): 监督过滤
- `source_type` (str, optional): 原作类型过滤
- `limit` (int, optional): 返回数量限制 (1-50)，默认 10
- `match_mode` (str, optional): `normal` | `recall` | `strict`（仅 `precise` 生效）
- `extra_scores` (bool, optional): 是否额外抓取站外评分（当前以 Filmarks 为主，慢），默认 `false`
- `debug_scores` (bool, optional): 返回评分抓取调试信息（用于定位站外评分抓取失败原因），默认 `false`

**示例**:
```bash
# 基础搜索
GET /api/v1/search?q=葬送的芙莉莲

# 提高召回
GET /api/v1/search?q=Frieren&match_mode=recall

# 获取站外评分（更慢）
GET /api/v1/search?q=Frieren&extra_scores=true

# 获取评分抓取调试信息
GET /api/v1/search?q=Frieren&extra_scores=true&debug_scores=true

# 带过滤条件
GET /api/v1/search?q=Frieren&year=2023&source=precise
```

**响应示例**:
```json
{
  "query": "Frieren",
  "source": "precise",
  "results": [
    {
      "name": "葬送のフリーレン",
      "name_cn": "葬送的芙莉莲",
      "ids": {
        "bgm_id": "400602",
        "mal_id": "52991",
        "anilist_id": "154587"
      },
      "scores": {
        "bgm": 8.6,
        "mal": 9.28,
        "anilist": 9.1
      },
      "time": {
        "year": 2023,
        "month": 10
      },
      "studio": "MADHOUSE",
      "confidence": 0.95,
      "matched_source": ["bangumi", "mal", "anilist"]
    }
  ],
  "total": 1,
  "filters_applied": {
    "year": 2023
  }
}
```

### POST /api/v1/search/
搜索动漫 (POST 方式)。

**请求体示例**:
```json
{
  "q": "葬送的芙莉莲",
  "source": "precise",
  "year": 2023,
  "match_mode": "recall",
  "extra_scores": true,
  "debug_scores": true,
  "limit": 5
}
```

---

## 导出

### GET /api/v1/export/csv
导出 CSV。

**查询参数**:
- `type` (str, optional): `airing` | `subscribed`，默认 `airing`

### GET /api/v1/export/json
导出 JSON。

**查询参数**:
- `type` (str, optional): `airing` | `subscribed`，默认 `airing`

---

## 统计

### GET /api/v1/stats/
获取统计信息。

**响应示例**:
```json
{
  "total_anime": 150,
  "airing_count": 50,
  "subscribed_count": 100,
  "score_distribution": {
    "8-9": 30,
    "7-8": 50
  },
  "year_distribution": {
    "2024": 50,
    "2023": 30
  },
  "last_updated": null
}
```

### GET /api/v1/stats/score-distribution
获取评分分布。

### GET /api/v1/stats/studio-ranking
获取制作公司排名。

**查询参数**:
- `limit` (int, optional): 返回数量

---

## 错误响应

错误时返回标准 HTTP 状态码，body 为 FastAPI 抛出的 `detail` 字段。

**示例**:
```json
{
  "detail": "Anime with bgm_id 123 not found"
}
```
