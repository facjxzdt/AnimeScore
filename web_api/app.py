from fastapi import FastAPI

import utils.get_ids
import web_api.meili_search
import threading
from starlette.responses import FileResponse
from web_api.wrapper import AnimeScore
from data.config import key
from pydantic import BaseModel
from data.config import work_dir
from deamon import updata_score,meili_update
import json
import uvicorn
import time
import schedule

animes_path = work_dir+'/data/jsons/score_sorted.json'
ans = AnimeScore()
app = FastAPI()
meili = web_api.meili_search.Meilisearch()

class PostBody(BaseModel):
    key: str

class IdBody(PostBody):
    bgm_id: str
    change_id: dict


def get_list(method):
    if method == 'sub':
        file = open(work_dir+'/data/jsons/sub_score_sorted.json')
    else:
        file = open(work_dir+'/data/jsons/score_sorted.json')
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

@app.get('/')
async def root():
    return {'status': 200}


@app.get('/air')
async def air():
    lists = get_list(method='air')
    return {'status': 200, 'body': lists}


@app.get('/sub')
def sub():
    lists = get_list(method='sub')
    return {'status': 200, 'body': lists}


@app.get('/search/{bgm_id}')
def search(bgm_id):
    result = ans.search_bgm_id(bgm_id)
    return {'status': 200, 'body': result}


@app.get('/search/meili/{string}')
def search_meili(string):
    result = ans.search_anime_name(string)
    return {'status': 200, 'body': result}
@app.get('/csv/{method}',status_code=200)
def get_csv(method):
    if method == 'air':
        filename = work_dir+'/data/score.csv'
    else:
        filename = work_dir+'/data/sub_score.csv'
    return FileResponse(
            filename,  # 这里的文件名是你要发送的文件名
            filename="score.csv", # 这里的文件名是你要给用户展示的下载的文件名，比如我这里叫lol.exe
        )

if __name__ == '__main__':
    ans.init()
    schedule.every().day.at("19:30").do(updata_score)
    schedule.every().day.at("19:30").do(meili_update())
    _deamon = deamon()
    uvicorn.run(app="app:app", host="0.0.0.0", port=5001)