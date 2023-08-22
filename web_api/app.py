from fastapi import FastAPI, routing
from web_api.wrapper import AnimeScore
from data.config import key
from pydantic import BaseModel

import json
import uvicorn

animes_path = '../data/jsons/score_sorted.json'
ans = AnimeScore()
app = FastAPI()


class PostBody(BaseModel):
    key: str
    method: str | None = None


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
    return {'status'}


if __name__ == '__main__':
    uvicorn.run(app="app:app", host="127.0.0.1", port=8080, reload=True)
