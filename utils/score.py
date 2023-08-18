import json

import utils.get_score
from data import config
from utils.logger import Log
from utils.get_score import get_single_score

scores_path = '../data/jsons/score.json'
scores_sorted_path = '../data/jsons/score_sorted.json'
animes_path = '../data/jsons/animes.json'

log_ts = Log(__name__).getlog()

global weights
weights = {}
exec('weights = config.'+config.weights,globals())

def store_score(dicts: dict):
    log_ts.info('正在存储分数')
    f1 = open(scores_sorted_path, 'w')
    f1.write(json.dumps(dicts, indent=4, separators=(',', ':')))
    f1.close()

def total_score():
    log_ts.info('正在计算总分')
    animes = json.load(open(animes_path, 'r'))
    scores = json.load(open(scores_path, 'r'))
    score = 0
    ani_score = {}
    anime = {}
    for k, v in scores.items():
        score = 0
        for k1, v1 in weights.items():
            if k1 in v.keys():
                score += v1 * float(v[k1])
            else:
                score = 'None'
                break
        if (score != 'None'):
            score = format(score, '.3f')
            anime['score'] = float(score)
        else:
            anime['score'] = score
        anime['name_cn'] = animes[k]['name_cn']
        anime['name'] = k
        anime['bgm_id'] = animes[k]['bgm_id']
        anime['bgm_score'] = scores[k]['bgm_score']
        anime['fm_score'] = scores[k]['fm_score']
        anime['mal_score'] = scores[k]['mal_score']
        if 'ank_score' in scores[k].keys():
            anime['ank_score'] = scores[k]['ank_score']
        else:
            anime['ank_score'] = 'None'
        if 'anl_score' in scores[k].keys():
            anime['anl_score'] = scores[k]['anl_score']
        else:
            anime['anl_score'] = 'None'
        anime['time'] = scores[k]['time']
        ani_score[animes[k]['name_cn']] = anime
        anime = {}
    store_score(ani_score)

def count_single_score(scores: dict):
    score = 0
    for k1, v1 in weights.items():
        if k1 in scores.keys():
            score += v1 * int(scores[k1])
        else:
            score = 'None'
            break
    if (score != 'None'):
        score = format(score, '.3f')
        scores['score'] = float(score)
    else:
        scores['score'] = score
    return scores