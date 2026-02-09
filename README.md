# AnimeScore

## 简介

一个汇集了各大评分网站评分的新番排名网站
对外提供API

### 网址：[https://rank.amoe.moe](https://rank.amoe.moe)
### API: [https://api.amoe.moe](https://amoe.moe)

## 效果

## 🆕 API v1 (推荐)

新版 RESTful API 已上线！提供更规范的接口设计和更丰富的功能。

**文档**: [API_V1.md](./API_V1.md)

**快速开始**:
```bash
# 获取正在放送的动漫
GET /api/v1/anime/airing

# 搜索动漫（多源交叉验证）
GET /api/v1/search?q=葬送的芙莉莲

# 健康检查
GET /api/v1/health/
```

---

## 快速启动(API)

### 0.使用我提供的服务
```
api.amoe.moe/air
```

### 1.本机部署

```bash
git clone https://github.com/facjxzdt/AnimeScore.git
cd AnimeScore
pip install -r requirements.txt
python ./web_api/main.py  # 新版入口
```
### 2.docker部署（推荐）

```bash
docker push facjxzdt/animescore:latest
docker run -d -p 5001:5001 --name animescore --network bridge facjxzdt/animescore
```
### 注意：容器每次启动都会需要10~20min获取分数，此时api无法访问

---

## API 端点 (旧版 - 仍然兼容)

> ⚠️ **注意**: 旧版 API 仍然可用，但建议使用 [新版 API v1](#-api-v1-推荐)

### 根路由

- **请求方法**：GET
- **路径**：`/`
- **描述**：根路由，用于测试API是否在线。
- **响应**：`{'status': 200}`

### 获取正在放送的动漫列表

- **请求方法**：GET
- **路径**：`/air`
- **描述**：获取当前正在放送的动漫评分列表。
- **新版替代**：`GET /api/v1/anime/airing`

### 搜索动漫 by ID `/search/{bgm_id}`

- **请求方法**：GET
- **路径**：`/search/{bgm_id}`
- **描述**：根据Bangumi ID搜索动漫信息。
- **新版替代**：`GET /api/v1/anime/{bgm_id}`

### 搜索动漫 by 名称 `/search/meili/{string}`

- **请求方法**：GET
- **路径**：`/search/meili/{string}`
- **描述**：根据动漫名称搜索动漫。
- **新版替代**：`GET /api/v1/search?q={string}&source=meili`

### 精确搜索 `/search/precise/{keyword}`

- **请求方法**：GET 或 POST
- **路径**：`/search/precise/{keyword}`
- **描述**：基于Bangumi、AniList、MyAnimeList(Jikan)三方API的交叉验证搜索方案，合并结果并补充缺失ID和评分。
- **新版替代**：`GET /api/v1/search?q={keyword}`

### 获取分数CSV文件 `/csv/{method}`

- **请求方法**：GET
- **路径**：`/csv/{method}`
- **描述**：下载CSV文件。
- **新版替代**：`GET /api/v1/export/csv?type={method}`

---

## API v1 新特性

| 特性 | 旧版 API | API v1 |
|------|---------|--------|
| RESTful 设计 | ❌ | ✅ |
| 版本控制 | ❌ | ✅ |
| 统一响应格式 | ❌ | ✅ |
| 健康检查 | ❌ | ✅ |
| 统计端点 | ❌ | ✅ |
| 多源搜索统一入口 | ❌ | ✅ |
| 标准 HTTP 状态码 | ❌ | ✅ |

---

## 说明：
- **搜索功能耗时较长，请设置较长超时**

## 开发

### 项目结构

```
AnimeScore/
├── apis/              # API客户端模块
│   ├── bangumi.py     # Bangumi API
│   ├── anilist.py     # AniList API
│   ├── mal.py         # MyAnimeList API
│   ├── anikore.py     # Anikore API
│   ├── filmarks.py    # Filmarks API
│   └── precise.py     # 多源交叉验证搜索
├── apps/              # 应用程序
├── data/              # 数据文件
├── utils/             # 工具函数
├── web/               # Flask Web界面
├── web_api/           # FastAPI API服务
│   ├── main.py        # 新版 API 入口
│   ├── api_v1/        # API v1 模块
│   │   ├── endpoints/ # API 端点
│   │   ├── schemas.py # 数据模型
│   │   └── router.py  # 路由聚合
│   └── app.py         # 旧版 API 入口（兼容）
└── requirements.txt   # 依赖
```

### 精确搜索模块使用

```python
from apis.precise import search_anime_precise

# 基础搜索
results = search_anime_precise("葬送的芙莉莲")

# 带过滤条件
results = search_anime_precise(
    keyword="芙莉莲",
    year=2023,
    studio="MADHOUSE",
    limit=5
)
```
