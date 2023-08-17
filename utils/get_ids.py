import json
import time

from utils.logger import Log
from apis.mal import MyAnimeList
from apis.anikore import Anikore
from apis.anilist import AniList
from apis.filmarks import Filmarks
from apis.bangumi import Bangumi
from data import config

animes_path = '../data/animes.json'

mal = MyAnimeList()
ank = Anikore()
anl = AniList()
fm = Filmarks()
bgm = Bangumi()

log_id = Log(__name__).getlog()

def get_ids():
    log_id.info('正在获取动画id，请稍后')
    animes = json.load(open(animes_path, 'r'))
    animes_count = animes['total']
    count = 0
    for k, v in animes.items():
        keep = True
        count_retry = 0
        while keep and count_retry < config.retry_max:
            if k != 'time':
                try:
                    v['mal_id'] = mal.search_anime(k)
                    v['ank_id'] = ank.get_ani_id(k)
                    v['anl_id'] = anl.get_al_id(k)
                    v['fm_id'] = fm.get_fm_score(k)
                    f1 = open(animes_path, 'w')
                    f1.write(json.dumps(animes, sort_keys=True, indent=4, separators=(',', ':')))
                    f1.close()
                    count += 1
                    log_id.info('动画id获取已完成: ' + str(count))
                    keep = False
                except:
                    count_retry += 1
                    time.sleep(config.time_sleep)
                    log_id.info('已重试：' + str(count_retry))
                    if count_retry == config.retry_max - 1:
                        try:
                            log_id.error('获取bgm_id: {}失败'.format(v['bgm_id']))
                        except:
                            pass
    log_id.info('获取动画分数成功数 {}'.format(str(count) + '/' + str(animes_count)))


def get_single_id(bgm_id: str):
    ids = {}
    name = bgm.get_anime_name(bgm_id)
    keep = True
    count_retry = 0
    while keep and count_retry < config.retry_max:
        try:
            ids['bgm_id'] = bgm_id
            ids['mal_id'] = mal.search_anime(name)
            ids['ank_id'] = ank.get_ani_id(name)
            ids['anl_id'] = anl.get_al_id(name)
            ids['fm_score'] = fm.get_fm_score(name)
            keep = False
        except:
            count_retry += 1
            time.sleep(config.time_sleep)
            log_id.info('已重试：' + str(count_retry))
    return ids