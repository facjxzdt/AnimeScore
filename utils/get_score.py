import json
import time

from utils.logger import Log
from utils.get_ids import get_single_id
from apis.mal import MyAnimeList
from apis.anikore import Anikore
from apis.anilist import AniList
from apis.filmarks import Filmarks
from apis.bangumi import Bangumi
from data import config

mal = MyAnimeList()
ank = Anikore()
anl = AniList()
fm = Filmarks()
bgm = Bangumi()

log_score = Log(__name__).getlog()

def get_time():
    time_dict = {}
    t = time.localtime()
    time_dict['year'] = t.tm_year
    time_dict['month'] = t.tm_mon
    time_dict['day'] = t.tm_mday
    return time_dict

def get_score(method):
    if method == 'sub':
        animes_path = '../data/jsons/sub.json'
        score_path = '../data/jsons/sub_score.json'
    else:
        animes_path = '../data/jsons/animes.json'
        score_path = '../data/jsons/score.json'
    log_score.info('正在获取动画评分')
    animes = json.load(open(animes_path, 'r'))
    animes_count = animes['total']
    scores = {}
    count = 0
    for k, v in animes.items():
        score = {}
        if k == 'total':
            pass
        elif v['ank_id'] == 'Error' and v['anl_id'] == 'Error':
            pass
        elif v['fm_id'] == '-' or k == 'time':
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
                    score['time'] = get_time()
                    scores[k] = score
                    f1 = open(score_path, 'w')
                    f1.write(json.dumps(scores, sort_keys=True, indent=4, separators=(',', ':')))
                    f1.close()
                    count += 1
                    log_score.info('动画评分获取已完成: ' + str(count))
                    keep = False
                except:
                    count_retry += 1
                    time.sleep(config.time_sleep)
                    log_score.info('重试: ' + str(count_retry))
                    if count_retry == config.retry_max - 1:
                        log_score.error('获取bgm_id: {}失败'.format(str(v['bgm_id'])))
        score = {}
    log_score.info('获取动画分数成功数 {}'.format(str(count)+'/'+str(animes_count)))

def get_single_score(bgm_id: str):
    scores = {}
    ids = get_single_id(bgm_id)
    if ids['ank_id'] == 'Error' and ids['anl_id'] == 'Error':
        pass
    elif ids['fm_score'] == '-':
        pass
    else:
        keep = True
        count_retry = 0
        while keep and count_retry < config.retry_max:
            try:
                scores['bgm_score'] = bgm.get_score(str(ids['bgm_id']))
                if ids['ank_id'] != 'Error':
                    scores['ank_score'] = 2 * float(ank.get_ani_score(ids['ank_id']))
                if ids['anl_id'] != 'Error':
                    scores['anl_score'] = anl.get_al_score(ids['anl_id'])
                if ids['mal_id'] != '404':
                    scores['mal_score'] = float(mal.get_anime_score(ids['mal_id']))
                scores['fm_score'] = 2 * float(ids['fm_score'])
                keep = False
            except:
                count_retry += 1
                time.sleep(config.time_sleep)
                log_score.info('重试: ' + str(count_retry))
                if count_retry == config.retry_max -1:
                    log_score.error('获取bgm_id: {}失败'.format(bgm_id))
    scores['name'] = bgm.get_anime_name(bgm_id)
    scores['ids'] = ids
    info = bgm.get_anime_info(bgm_id)
    scores['poster'] = info['images']['large']
    scores['name_cn'] = info['name_cn']
    scores['time'] = get_time()
    scores['bgm_id'] = ids['bgm_id']
    return scores
