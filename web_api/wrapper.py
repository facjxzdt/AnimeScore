import utils.get_ids
import utils.get_score
import utils.json2csv
import utils.score
import utils.sub_anime
import utils.tools

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
        self.meili = Meilisearch

    #类封装
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

    def Meilisearch(self):
        return self.Meilisearch()

    #方法封装
    def get_ids(self):
        return utils.get_ids.get_ids()

    def get_single_id(self):
        return utils.get_ids.get_single_id()

    def get_score(self):
        return utils.get_score.get_score()

    def get_single_score(self):
        return utils.get_score.get_single_score()

    def total_score(self):
        return utils.score.total_score()

    def json2csv(self):
        return utils.json2csv.json2csv()
