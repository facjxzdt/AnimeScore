import json
import time
import threading

from utils.logger import Log
from apis.mal import MyAnimeList
from apis.anikore import Anikore
from apis.anilist import AniList
from apis.filmarks import Filmarks
from apis.bangumi import Bangumi
from data import config

animes_path = config.work_dir + "/data/jsons/animes.json"
animes = {}
ids = {}

mal = MyAnimeList()
ank = Anikore()
anl = AniList()
fm = Filmarks()
bgm = Bangumi()

log_id = Log(__name__).getlog()


def get_mal_id(string, dicts: dict):
    dicts["mal_id"] = mal.search_anime(string)
    time.sleep(1)


def get_ank_id(string, dicts: dict):
    dicts["ank_id"] = ank.get_ani_id(string)
    time.sleep(1)


def get_anl_id(string, dicts: dict):
    dicts["anl_id"] = anl.get_al_id(string)
    time.sleep(1)


def get_fm_id(string, dicts: dict):
    dicts["fm_id"] = fm.get_fm_score(string)
    time.sleep(1)


def create_threads(dicts: dict, string: str):
    tlist = []
    t1 = threading.Thread(
        target=get_fm_id,
        args=(
            string,
            dicts,
        ),
    )
    t2 = threading.Thread(
        target=get_mal_id,
        args=(
            string,
            dicts,
        ),
    )
    t3 = threading.Thread(
        target=get_ank_id,
        args=(
            string,
            dicts,
        ),
    )
    t4 = threading.Thread(
        target=get_anl_id,
        args=(
            string,
            dicts,
        ),
    )
    t1.start()
    log_id.debug("{}线程创建成功".format(t1.name))
    t2.start()
    log_id.debug("{}线程创建成功".format(t2.name))
    t3.start()
    log_id.debug("{}线程创建成功".format(t3.name))
    t4.start()
    log_id.debug("{}线程创建成功".format(t4.name))
    tlist.append(t1)
    tlist.append(t2)
    tlist.append(t3)
    tlist.append(t4)
    for t in tlist:
        t.join()


def get_ids():
    log_id.info("正在获取动画id，请稍后")
    global animes
    animes = json.load(open(animes_path, "r"))
    animes_count = animes["total"]
    count = 0
    for k, v in animes.items():
        keep = True
        count_retry = 0
        while keep and count_retry < config.retry_max:
            if k != "time":
                try:
                    create_threads(v, k)
                    f1 = open(animes_path, "w")
                    f1.write(
                        json.dumps(
                            animes, sort_keys=True, indent=4, separators=(",", ":")
                        )
                    )
                    f1.close()
                    count += 1
                    log_id.info("动画id获取已完成: " + str(count))
                    keep = False
                except:
                    count_retry += 1
                    time.sleep(config.time_sleep)
                    log_id.info("已重试：" + str(count_retry))
                    if count_retry == config.retry_max - 1:
                        try:
                            log_id.error("获取bgm_id: {}失败".format(v["bgm_id"]))
                        except:
                            pass
    log_id.info("获取动画分数成功数 {}".format(str(count) + "/" + str(animes_count)))


def get_single_id(bgm_id: str):
    global ids
    ids = {}
    name = bgm.get_anime_name(bgm_id)
    keep = True
    count_retry = 0
    while keep and count_retry < config.retry_max:
        try:
            ids["bgm_id"] = bgm_id
            create_threads(ids, name)
            keep = False
        except:
            count_retry += 1
            time.sleep(config.time_sleep)
            log_id.info("已重试：" + str(count_retry))
    return ids
