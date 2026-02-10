# AnimeScore

AnimeScore 是一个聚合多平台动漫评分并提供 API 的项目。

当前仅保留 `API v1`，入口为 FastAPI。

## 快速开始

### 1) 本机运行

```bash
git clone https://github.com/facjxzdt/AnimeScore.git
cd AnimeScore

# 推荐使用项目虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 启动 API
python start_api.py
```

启动后：

- Docs: `http://localhost:5001/docs`
- Health: `http://localhost:5001/api/v1/health/`

### 2) Docker 运行

```bash
docker build -t animescore:latest .
docker run -d -p 5001:5001 --name animescore animescore:latest
```

## API 文档

完整接口文档见 `API_V1.md`。

常用接口：

- `GET /api/v1/anime/airing`
- `GET /api/v1/search?q=葬送的芙莉莲`
- `GET /api/v1/search?q=超时空辉夜姬&extra_scores=true&debug_scores=true`

## 搜索说明

`/api/v1/search` 默认使用 `precise` 多源搜索，支持：

- `match_mode`: `normal|recall|strict`
- `extra_scores=true`: 追加站外评分抓取（当前以 Filmarks 为主）
- `debug_scores=true`: 返回评分抓取调试信息（定位抓取失败原因）

## 项目结构

```text
AnimeScore/
├── apis/                  # 各站点 API 客户端 + precise 搜索整合
├── web_api/               # FastAPI 入口与 v1 路由
│   ├── main.py            # API 主入口
│   └── api_v1/            # v1 endpoints/schemas/router
├── data/                  # 本地数据与映射
├── utils/                 # 工具模块
├── scripts/release_check.sh
├── API_V1.md
└── start_api.py
```

## 发布前检查

```bash
./scripts/release_check.sh
```

该脚本会做：

- Python 语法检查
- API 关键模块导入检查
- 基本文档链接检查

