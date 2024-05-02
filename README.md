# AnimeScore

## 简介

一个汇集了各大评分网站评分的新番排名网站
对外提供API

### 网址：[https://rank.amoe.moe](https://rank.amoe.moe)
### API: [https://api.amoe.moe](https://amoe.moe)

## 效果

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
python ./web_api/app.py
```
### 2.docker部署（推荐）

```bash
docker push facjxzdt/animescore:latest
docker run -d -p 5001:5001 --name animescore --network bridge facjxzdt/animescore
```
### 注意：容器每次启动都会需要10~20min获取分数，此时api无法访问

## API 端点

### 根路由

- **请求方法**：GET
- **路径**：`/`
- **描述**：根路由，用于测试API是否在线。
- **响应**：`{'status': 200}`

### 获取正在放送的动漫列表

- **请求方法**：GET
- **路径**：`/air`
- **描述**：获取当前正在放送的动漫评分列表。
- **响应**：
  ```json
  {
    "status": 200,
    "body": ["body": {
    "30歳まで童貞だと魔法使いになれるらしい": {
      "score": 6.376,
      "name_cn": "到了30岁还是处男，似乎会变成魔法师",
      "name": "30歳まで童貞だと魔法使いになれるらしい",
      "bgm_id": 445708,
      "poster": "http://lain.bgm.tv/pic/cover/l/a6/af/445708_eM6dm.jpg",
      "mal_score": 7.63,
      "bgm_score": 5.5,
      "fm_score": 7,
      "ids": {
        "bgm_id": 445708,
        "mal_id": "55973",
        "ank_id": "14321",
        "anl_id": 167087,
        "fm_score": "3.5"
      },
      "ank_score": 7.2,
      "anl_score": 7.35,
      "time": {
        "day": 24,
        "month": 3,
        "year": 2024
      }
    }]
  }


### 搜索动漫 by ID `/search/{bgm_id}`

- **请求方法**：GET
- **路径**：`/search/{bgm_id}`
- **描述**：根据Bangumi ID搜索动漫信息。
- **参数**：
  - `bgm_id`: 要搜索的动漫的Bangumi ID。
- **响应**：同上

### 搜索动漫 by 名称 `/search/meili/{string}`

- **请求方法**：GET
- **路径**：`/search/meili/{string}`
- **描述**：根据动漫名称搜索动漫。
- **参数**：
  - `string`: 要搜索的动漫名称。
- **响应**：
  ```json
  {
    "status": 200,
    "body": [/* 搜索结果列表 */]
  }
  ```

### 获取分数CSV文件 `/csv/air`

- **请求方法**：GET
- **路径**：`/csv/{method}`
- **描述**：下载CSV文件。
- **响应**：
  - 文件下载。

## 说明：
- **meilisearch密匙和api设置在/data/config.py中 如果使用docker部署，可以设置环境变量`meili_url`和`meili_key`**
- **使用搜索功能后搜索到的动画会直接存到meilisearch中，调用时可以先看看meilisearch中有没有**
- **搜索功能耗时较长，请设置较长超时**
