import json
import time

from utils.logger import Log
from apis.mal import MyAnimeList
from apis.anikore import Anikore
from apis.anilist import AniList
from apis.filmarks import Filmarks
from data import config

animes_path = '../data/animes.json'

mal = MyAnimeList()
ank = Anikore()
anl = AniList()
fm = Filmarks()

log_id = Log(__name__).getlog()

def get_ids():
    log_id.info('正在获取动画id，请稍后')
    animes = json.load(open(animes_path, 'r'))
    count = 0
    for k, v in animes.items():
        keep = True
        count_retry = 0
        while keep and count_retry < config.retry_max:
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
