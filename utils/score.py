import json
from data import config
from utils.logger import Log

scores_path = '../data/score.json'
scores_sorted_path = '../data/score_sorted.json'
animes_path = '../data/animes.json'

log_ts = Log(__name__).getlog()

def store_score(dicts: dict):
    log_ts.info('正在存储分数')
    f1 = open(scores_sorted_path, 'w')
    f1.write(json.dumps(dicts, indent=4, separators=(',', ':')))
    f1.close()


def total_score():
    log_ts.info('正在计算总分')
    animes = json.load(open(animes_path, 'r'))
    global weights
    weights = {}
    exec('weights = config.'+config.weights,globals())
    scores = json.load(open(scores_path, 'r'))
    score = 0
    ani_score = {}
    anime = {}
    for k, v in scores.items():
        score = 0
        for k1, v1 in weights.items():
            if k1 in v.keys():
                score += v1 * int(v[k1])
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
        ani_score[animes[k]['name_cn']] = anime
        anime = {}
    store_score(ani_score)