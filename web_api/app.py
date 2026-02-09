import json
import threading
import time
from typing import Optional

import schedule
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.responses import FileResponse

from apis.precise import search_anime_precise
from data.config import work_dir
from deamon import updata_score
from web_api.wrapper import AnimeScore

animes_path = work_dir + "/data/jsons/score_sorted.json"
ans = AnimeScore()
app = FastAPI()


class PostBody(BaseModel):
    key: str


class IdBody(PostBody):
    bgm_id: str
    change_id: dict


class PreciseSearchQuery(BaseModel):
    """精确搜索查询参数"""

    year: Optional[int] = None
    month: Optional[int] = None
    studio: Optional[str] = None
    director: Optional[str] = None
    source: Optional[str] = None
    limit: int = 10


def get_list(method):
    if method == "sub":
        file = open(work_dir + "/data/jsons/sub_score_sorted.json")
    else:
        file = open(work_dir + "/data/jsons/score_sorted.json")
    scores = file
    return json.load(scores)


def deamon(interval=1):
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


@app.get("/")
async def root():
    return {"status": 200}


@app.get("/air")
async def air():
    lists = get_list(method="air")
    return {"status": 200, "body": lists}


@app.get("/sub")
def sub():
    lists = get_list(method="sub")
    return {"status": 200, "body": lists}


@app.get("/search/{bgm_id}")
def search(bgm_id):
    result = ans.search_bgm_id(bgm_id)
    return {"status": 200, "body": result}


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
    多源交叉验证精确搜索

    支持同时查询 Bangumi、AniList、MAL 三个平台并交叉验证

    - **keyword**: 搜索关键词（动漫名称）
    - **year**: 可选，年份过滤，如 2023
    - **month**: 可选，月份过滤，如 7
    - **studio**: 可选，制作公司过滤，如 "MAPPA"
    - **director**: 可选，监督过滤
    - **source**: 可选，原作类型过滤，如 "漫画"
    - **limit**: 返回结果数量限制，默认10
    """
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


@app.post("/search/precise")
def search_precise_post(query: PreciseSearchQuery, keyword: str):
    """
    多源交叉验证精确搜索 (POST方式)

    请求体包含过滤参数，URL参数包含关键词
    """
    results = search_anime_precise(
        keyword=keyword,
        year=query.year,
        month=query.month,
        studio=query.studio,
        director=query.director,
        source=query.source,
        top_n=query.limit,
    )
    return {"status": 200, "body": results}


@app.get("/csv/{method}", status_code=200)
def get_csv(method):
    if method == "air":
        filename = work_dir + "/data/score.csv"
    else:
        filename = work_dir + "/data/sub_score.csv"
    return FileResponse(
        filename,
        filename="score.csv",
    )


if __name__ == "__main__":
    ans.init()
    schedule.every().day.at("19:30").do(updata_score)
    _deamon = deamon()
    uvicorn.run(app="app:app", host="0.0.0.0", port=5001)
