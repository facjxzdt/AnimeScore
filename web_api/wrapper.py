import utils.get_ids
import utils.get_score
import utils.json2csv
import utils.score
import utils.sub_anime
import utils.logger
import utils.errors as errors
import apps.search
import json
import os
import web.sql_add as sql_add

from data.config import ttl, max_size, work_dir
from utils.tools import Tools
from apis.bangumi import Bangumi
from apis.anilist import AniList
from apis.mal import MyAnimeList
from apis.filmarks import Filmarks
from apis.anikore import Anikore
from cachetools import cached, TTLCache

logger = utils.logger.Log()
cache = TTLCache(max_size, ttl)


class AnimeScore:
    def __init__(self):
        self.version = "v0.2"
        self.mal = MyAnimeList()
        self.ank = Anikore()
        self.anl = AniList()
        self.fm = Filmarks()
        self.bgm = Bangumi()
        self.tools = Tools()

    def init(self):
        first = False
        logger.logger.info("正在初始化")
        if os.path.exists(work_dir + "/data/init.lock"):
            pass
        else:
            file = open(work_dir + "/data/init.lock", "w")
            first = True
        logger.logger.info("测试网络")
        if self.tools.check_net():
            logger.logger.info("可以访问api")
        else:
            raise errors.NetworkError()

        if first:
            self.bgm.get_season_name()
            utils.get_ids.get_ids()
            utils.get_score.get_score(method="air")
            utils.score.total_score(method="air")
            utils.json2csv.json2csv(method="air")
            os.makedirs(work_dir + "/web/instance", exist_ok=True)
            sql_add.store_data()
            file1 = open(work_dir + "/data/database.lock", "w")
            file1.close()

    # 类封装
    # Bangumi类下各方法
    # get_info(): 获取bgm每日放送
    # load_oneday_json(weekday: int): 从~/data/json/season.json下获取某一天的新番
    # get_season_name(): 从season.json提取信息到anime.json下
    # get_score(bgm_id: str): 获取bgm_id=bgm_id的动画的bgm评分
    # get_score_bs4(bgm_id): 使用bs4的get_score替换
    # search_anime(anime_name: str): 向bgm api发送search post请求
    # search_cli: bgm动画搜索的cli实现
    def Bangumi(self):
        return self.bgm

    def Anilist(self):
        return self.anl

    def MyAnimeList(self):
        return self.mal

    def Filmarks(self):
        return self.fm

    def Anikore(self):
        return self.ank

    # 方法封装
    def get_ids(self):  # 获取anime.json中动画的id
        return utils.get_ids.get_ids()

    @cached(cache)
    def get_single_id(self, bgm_id):  # bgm_id: str
        return utils.get_ids.get_single_id(bgm_id)

    def get_score(self, method):  # method='sub'or'air'
        return utils.get_score.get_score(method)

    @cached(cache)
    def get_single_score(self, bgm_id):
        return utils.get_score.get_single_score(bgm_id)

    def total_score(self, method):  # method='sub'or'air'
        return utils.score.total_score(method)

    def json2csv(self, method):  # method='sub'or'air'
        return utils.json2csv.json2csv(method)

    def sub_anime(self, method, anime_name, bgm_id):
        return utils.sub_anime.sub_animes(
            method=method, anime_name=anime_name, bgm_id=bgm_id
        )

    @cached(cache)
    def search_bgm_id(self, bgm_id=None, method="bgm_id"):
        if method == "bgm_id":
            info = utils.score.count_single_score(
                utils.get_score.get_single_score(bgm_id)
            )
            return info
        else:
            return apps.search.search_anime()

    # sub_anime函数参数说明
    # 必须参数: method='bgm_id' or 'name'
    # name: 为动画名 将会调用控制台进行cli交互
    # bgm_id: 为bgm网站id 无需交互
    # 故name适合本地添加 bgm_id本地or api添加都可以
    def sub_anime(
        self, method, anime_name=None, bgm_id=None
    ):  # sub_animes(method='name'or'bgm_id',anime_name=None,bgm_id=None)
        bgm_id = utils.sub_anime.sub_animes(
            method=method, anime_name=anime_name, bgm_id=bgm_id
        )
        info = utils.score.count_single_score(utils.score.get_single_score(bgm_id))
        score_path = work_dir + "/data/jsons/sub_score_sorted.json"
        scores_exist = json.load(open(score_path, "r"))
        scores_exist[info["name"]] = info
        f = open(score_path, "w")
        f.write(
            json.dumps(scores_exist, sort_keys=True, indent=4, separators=(",", ":"))
        )
        f.close()
        return True

    def update_all_anime(self, method):
        utils.get_score.get_score(method)
        utils.score.total_score(method)
        utils.json2csv.json2csv(method)

    def update_air_anime(self):
        utils.get_score.get_score(method="air")
        self.update_all_anime(method="air")

    def update_single_score(self, bgm_id):
        utils.get_score.update_score(bgm_id)

    def change_id(self, bgm_id: str, change_id: dict):
        filename = work_dir + "/data/jsons/sub.json"
        sub = json.load(open(filename, "r"))
        for k, v in sub.items():
            if not isinstance(v, dict):
                continue
            if str(v.get("bgm_id")) == str(bgm_id):
                for k1, v1 in change_id.items():
                    v[k1] = v1
        utils.get_score.update_score(bgm_id)
        f1 = open(filename, "w")
        f1.write(json.dumps(sub, sort_keys=True, indent=4, separators=(",", ":")))
        f1.close()
