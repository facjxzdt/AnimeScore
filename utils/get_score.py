import json
import time
import threading

from web_api.meili_search import Meilisearch
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
meili = Meilisearch()

score = {}
score_1 = {}
score_2 = {}

log_score = Log(__name__).getlog()

def get_bgm_id(bgm_id,score: dict):
    score['bgm_score'] = bgm.get_score(bgm_id)
    time.sleep(1)

def get_ank_id(ank_id,score: dict):
    if ank_id != 'Error':
        score['ank_score'] = 2 * float(ank.get_ani_score(ank_id))
    time.sleep(1)

def get_anl_id(anl_id,score: dict):
    if anl_id != 'Error':
        score['anl_score'] = anl.get_al_score(anl_id)
    time.sleep(1)

def get_mal_id(mal_id,score: dict):
    if mal_id != '404':
        mal_score = mal.get_anime_score(mal_id)
        if mal_score != 'N/A':
            score['mal_score'] = float(mal_score)
    time.sleep(1)

def create_threads(dicts:dict,score: dict):
    tlist = []
    t1 = threading.Thread(target=get_bgm_id, args=(str(dicts['bgm_id']),score,))
    t2 = threading.Thread(target=get_mal_id, args=(str(dicts['mal_id']),score,))
    t3 = threading.Thread(target=get_ank_id, args=(str(dicts['ank_id']),score,))
    t4 = threading.Thread(target=get_anl_id, args=(str(dicts['anl_id']),score,))
    t1.start()
    log_score.debug('{}线程创建成功'.format(t1.name))
    t2.start()
    log_score.debug('{}线程创建成功'.format(t2.name))
    t3.start()
    log_score.debug('{}线程创建成功'.format(t3.name))
    t4.start()
    log_score.debug('{}线程创建成功'.format(t4.name))
    tlist.append(t1)
    tlist.append(t2)
    tlist.append(t3)
    tlist.append(t4)
    for t in tlist:
        t.join()

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
        global score
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
                    global score
                    create_threads(v,score)
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
    global score_1
    score_1 = {}
    ids = get_single_id(bgm_id)
    if ids['ank_id'] == 'Error' and ids['anl_id'] == 'Error':
        pass
    elif ids['fm_id'] == '-':
        pass
    else:
        keep = True
        count_retry = 0
        while keep and count_retry < config.retry_max:
            try:
                create_threads(ids,score_1)
                score_1['fm_score'] = 2 * float(ids['fm_id'])
                keep = False
            except:
                count_retry += 1
                time.sleep(config.time_sleep)
                log_score.info('重试: ' + str(count_retry))
                if count_retry == config.retry_max -1:
                    log_score.error('获取bgm_id: {}失败'.format(bgm_id))
    score_1['name'] = bgm.get_anime_name(bgm_id)
    score_1['ids'] = ids
    info = bgm.get_anime_info(bgm_id)
    score_1['poster'] = info['images']['large']
    score_1['name_cn'] = info['name_cn']
    score_1['time'] = get_time()
    score_1['bgm_id'] = ids['bgm_id']
    return score_1

def update_score(bgm_id: str):
    # 该函数用于更新sub下的分数
    # air由于会每日自动更新 故不添加update_score
    meili = Meilisearch()
    bgm_id = str(bgm_id)
    score_path = '../data/jsons/sub_score_sorted.json'
    info = meili.index.search(
        bgm_id,
        {
            'filter':['id={}'.format(bgm_id)]
        }
    )['hits'][0]
    global score_2
    score_2 = {}
    create_threads(info['ids'],score_2)
    score_2['fm_score'] = fm.get_fm_score(info['name'])
    info['bgm_score'] = score_2['bgm_score']
    info['fm_score'] = score_2['fm_score']
    info['mal_score'] = score_2['mal_score']
    info['ank_score'] = score_2['ank_score']
    info['anl_score'] = score_2['anl_score']
    info['time'] = get_time()
    meili.add_single_anime(dict(info))
    #更新json
    scores = json.load(open(score_path,'r'))
    scores[info['name']] = info
    f1 = open(score_path, 'w')
    f1.write(json.dumps(scores, sort_keys=True, indent=4, separators=(',', ':')))
    f1.close()