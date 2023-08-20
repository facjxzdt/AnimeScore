import utils.get_ids
import utils.get_score
import utils.json2csv
import utils.score
import utils.sub_anime
import utils.tools
import apps.search

from apis.bangumi import Bangumi
from apis.anilist import AniList
from apis.mal import MyAnimeList
from apis.filmarks import Filmarks
from apis.anikore import Anikore
from meili_search import Meilisearch

class AnimeScore:
    def __init__(self):
        self.version = 'v0.2'
        self.mal = MyAnimeList()
        self.ank = Anikore()
        self.anl = AniList()
        self.fm = Filmarks()
        self.bgm = Bangumi()
        self.meili = Meilisearch()

    #类封装
    #Bangumi类下各方法
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

    # Meilisearch类的方法
    # add_anime2search(method='sub' or 'air') 将订阅动画评分或放送中动画评分同步到meilisearch
    # tips: 该方法是完全同步 即sub_score_sorted.json或score_sorted.json完全同步到meilisearch
    # search_anime(string: str): 在meilisearch中搜索
    # add_single_anime(dicts: dict): 将dicts同步到meilisearch
    def Meilisearch(self):
        return self.Meilisearch()

    #方法封装
    def get_ids(self):# 获取anime.json中动画的id
        return utils.get_ids.get_ids()

    def get_single_id(self):# bgm_id: str
        return utils.get_ids.get_single_id()

    def get_score(self):# method='sub'or'air'
        return utils.get_score.get_score()

    def get_single_score(self):
        return utils.get_score.get_single_score()

    def total_score(self):# method='sub'or'air'
        return utils.score.total_score()

    def json2csv(self):# method='sub'or'air'
        return utils.json2csv.json2csv()

    def sub_anime(self):
        return utils.sub_anime()

    def search_bgm_id(self,bgm_id=None,method='bgm_id'):
        if method == 'bgm_id':
            info = utils.score.count_single_score(utils.get_score.get_single_score(bgm_id))
            self.meili.add_single_anime(info)
            return info
        else:
            return apps.search.search_anime()

    def search_anime_name(self):
        return self.meili.search_anime()

    # sub_anime函数参数说明
    # 必须参数: method='bgm_id' or 'name'
    # name: 为动画名 将会调用控制台进行cli交互
    # bgm_id: 为bgm网站id 无需交互
    # 故name适合本地添加 bgm_id本地or api添加都可以
    def sub_anime(self,method='name'or'bgm_id',anime_name=None,bgm_id=None):# sub_animes(method='name'or'bgm_id',anime_name=None,bgm_id=None)
        utils.sub_anime.sub_animes(method=method,anime_name=anime_name,bgm_id=bgm_id)
        utils.get_score.get_score('sub')
        utils.score.total_score('sub')
        self.meili.add_anime2search('sub')

ans = AnimeScore()
ans.sub_anime(method='bgm_id',bgm_id=428735)