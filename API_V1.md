# AnimeScore API v1 文档

## 概述

API v1 采用 RESTful 设计，提供标准化的响应格式和版本控制。

**基础 URL**: `/api/v1`

## 响应格式

### 成功响应

```json
{
  "success": true,
  "data": { ... },
  "message": null
}
```

### 错误响应

```json
{
  "success": false,
  "error_code": "NOT_FOUND",
  "message": "Anime not found",
  "details": { ... }
}
```

## 端点列表

### 健康检查

#### GET /api/v1/health/

返回 API 运行状态。

**响应示例**:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00",
  "uptime": 3600,
  "services": {
    "api": true,
    "data_files": true,
    "meilisearch": true
  }
}
```

#### GET /api/v1/health/ping

快速健康检查。

**响应**:
```json
{"message": "pong"}
```

---

### 动漫列表

#### GET /api/v1/anime/airing

获取正在放送的动漫列表。

**查询参数**:
- `limit` (int, optional): 返回数量限制 (1-100)
- `sort_by` (str, optional): 排序字段 (`score`, `name`, `time`)

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

---

#### GET /api/v1/anime/subscribed

获取订阅的动漫列表。

**查询参数**:
- `limit` (int, optional): 返回数量限制
- `sort_by` (str, optional): 排序字段

---

#### GET /api/v1/anime/season/current

获取当前季番。

**响应示例**:
```json
{
  "season": {
    "year": 2024,
    "season": "winter",
    "name": "2024年1月冬番"
  },
  "anime_list": [ ... ],
  "total": 50,
  "updated_at": "2024-01-15T10:00:00"
}
```

---

#### GET /api/v1/anime/{bgm_id}

根据 Bangumi ID 获取动漫详情。

**路径参数**:
- `bgm_id` (str, required): Bangumi 动漫 ID

---

### 搜索

#### GET /api/v1/search/

搜索动漫。

**查询参数**:
- `q` (str, required): 搜索关键词
- `source` (str, optional): 搜索源 (`precise`, `meili`, `bangumi`)，默认 `precise`
- `year` (int, optional): 年份过滤
- `month` (int, optional): 月份过滤
- `studio` (str, optional): 制作公司过滤
- `director` (str, optional): 监督过滤
- `limit` (int, optional): 返回数量限制 (1-50)，默认 10

**示例**:
```bash
# 基础搜索
GET /api/v1/search?q=葬送的芙莉莲

# 带过滤条件
GET /api/v1/search?q=Frieren&year=2023&source=precise

# MeiliSearch 搜索
GET /api/v1/search?q=芙莉莲&source=meili
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
      "year": 2023,
      "studio": "MADHOUSE",
      "confidence": 0.95,
      "matched_source": ["bangumi", "mal", "anilist"]
    }
  ],
  "total": 3,
  "filters_applied": {
    "year": 2023
  }
}
```

---

#### POST /api/v1/search/

搜索动漫 (POST 方式)。

**请求体**:
```json
{
  "q": "葬送的芙莉莲",
  "source": "precise",
  "year": 2023,
  "studio": "MADHOUSE",
  "limit": 5
}
```

---

### 导出

#### GET /api/v1/export/csv

导出 CSV 文件。

**查询参数**:
- `type` (str, optional): 导出类型 (`airing`, `subscribed`)，默认 `airing`

**示例**:
```bash
GET /api/v1/export/csv?type=airing
```

---

#### GET /api/v1/export/json

导出 JSON 文件。

**查询参数**:
- `type` (str, optional): 导出类型 (`airing`, `subscribed`)

---

### 统计

#### GET /api/v1/stats/

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
  "last_updated": "2024-01-15T10:00:00"
}
```

---

#### GET /api/v1/stats/score-distribution

获取评分分布。

---

#### GET /api/v1/stats/studio-ranking

获取制作公司排名。

**查询参数**:
- `limit` (int, optional): 返回数量

---

## 搜索源说明

| 搜索源 | 说明 | 适用场景 |
|--------|------|----------|
| `precise` | 多源交叉验证搜索 | 需要完整信息和准确匹配 |
| `meili` | MeiliSearch 本地搜索 | 快速搜索本地数据 |
| `bangumi` | Bangumi API 搜索 | 获取 Bangumi 最新数据 |

---

## 旧版 API 兼容

旧版 API 仍然可用，但建议使用新版 API v1。

| 旧版端点 | 新版端点 | 说明 |
|----------|----------|------|
| `GET /air` | `GET /api/v1/anime/airing` | 获取正在放送列表 |
| `GET /sub` | `GET /api/v1/anime/subscribed` | 获取订阅列表 |
| `GET /search/{bgm_id}` | `GET /api/v1/anime/{bgm_id}` | 根据 ID 获取 |
| `GET /search/meili/{string}` | `GET /api/v1/search?q={string}&source=meili` | Meili 搜索 |
| `GET /search/precise/{keyword}` | `GET /api/v1/search?q={keyword}` | 精确搜索 |
| `GET /csv/{method}` | `GET /api/v1/export/csv?type={method}` | 导出 CSV |

---

## 错误码

| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| `BAD_REQUEST` | 400 | 请求参数错误 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |
