import json
import time

from apis.mal import MyAnimeList
from apis.anikore import Anikore
from apis.anilist import AniList
from apis.filmarks import Filmarks
from apis.bangumi import Bangumi
from data import config

animes_path = '../data/animes.json'
score_path = '../data/score.json'

mal = MyAnimeList()
ank = Anikore()
anl = AniList()
fm = Filmarks()
bgm = Bangumi()


def get_score():
    print('正在获取动画评分')
    animes = json.load(open(animes_path, 'r'))
    scores = {}
    count = 0
    for k, v in animes.items():
        score = {}
        if v['ank_id'] == 'Error' and v['anl_id'] == 'Error':
            pass
        elif v['fm_id'] == '-':
            pass
        else:
            keep = True
            count_retry = 0
            while keep and count_retry < config.retry_max:
                try:
                    score['bgm_score'] = bgm.get_score(str(v['bgm_id']))
                    if v['ank_id'] != 'Error':
                        score['ank_score'] = 2 * float(ank.get_ani_score(v['ank_id']))
                    if v['anl_id'] != 'Error':
                        score['anl_score'] = anl.get_al_score(v['anl_id'])
                    if v['mal_id'] != '404':
                        score['mal_score'] = float(mal.get_anime_score(v['mal_id']))
                    score['fm_score'] = 2 * float(v['fm_id'])
                    scores[k] = score
                    f1 = open(score_path, 'w')
                    f1.write(json.dumps(scores, sort_keys=True, indent=4, separators=(',', ':')))
                    f1.close()
                    count += 1
                    print('已完成: ' + str(count))
                    keep = False
                except:
                    count_retry += 1
                    time.sleep(config.time_sleep)
                    print('重试: ' + str(count_retry))
        score = {}
