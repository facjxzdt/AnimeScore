from fastapi import FastAPI

import utils.get_ids
import web_api.meili_search
from starlette.responses import FileResponse
from web_api.wrapper import AnimeScore
from data.config import key
from pydantic import BaseModel

import json
import uvicorn

animes_path = '../data/jsons/score_sorted.json'
ans = AnimeScore()
app = FastAPI()
meili = web_api.meili_search.Meilisearch()


class PostBody(BaseModel):
    key: str
    method: str | None = None

class IdBody(PostBody):
    bgm_id: str
    change_id: dict


def get_list(method):
    if method == 'sub':
        file = open('../data/jsons/sub_score_sorted.json')
    else:
        file = open('../data/jsons/score_sorted.json')
    scores = file
    return json.load(scores)


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


@app.post('/update_anime')
def update_all_anime(body: PostBody):
    if body.key == key:
        ans.update_all_anime(method=body.method)
        return {'status': 200, 'body': 'OK'}
    return {'status': 403, 'body': 'Key error!'}


@app.post('/update_air_anime')
def update_air_anime(body: PostBody):
    if body.key == key:
        ans.update_air_anime()
        return {'status': 200, 'body': 'OK'}
    return {'status':403, 'body':'Key error!'}

@app.post('/meili_update/{method}')
def meili_update(method,body: PostBody):
    if body.key == key:
        meili.add_anime2search(method)
        return {'status': 200, 'body': 'OK'}
    return {'status':403, 'body':'Key error!'}

@app.get('/csv/{method}',status_code=200)
def get_csv(method):
    if method == 'air':
        filename = '../data/score.csv'
    else:
        filename = '../data/sub_score.csv'
    return FileResponse(
            filename,  # 这里的文件名是你要发送的文件名
            filename="score.csv", # 这里的文件名是你要给用户展示的下载的文件名，比如我这里叫lol.exe
        )

@app.post('/change_id')
def change_id(body: IdBody):
    if body.key == key:
        utils.get_ids.change_id(bgm_id=body.bgm_id,change_id=body.change_id)

if __name__ == '__main__':
    ans.init()
    uvicorn.run(app="app:app", host="127.0.0.1", port=5001, reload=True)
