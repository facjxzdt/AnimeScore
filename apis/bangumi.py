import requests
import json

from bs4 import BeautifulSoup
from data import config


class Bangumi:
    def __init__(self):
        self.json_path = '../data/season.json'
        self.animes_path = '../data/animes.json'
        self.bangumi_api = "https://api.bgm.tv"
        self.bs4_url = 'https://bgm.tv'
        self.headers = {'user-agent': 'facjxzdt/autobangumi'}

    def get_info(self):
        # 获取bgm新番
        self.bgm_calendar = requests.get(self.bangumi_api + '/calendar', timeout=config.timeout).json()

        # 保存json
        self.f = open(self.json_path, 'w')
        self.f.write(json.dumps(self.bgm_calendar, sort_keys=True, indent=4, separators=(',', ':')))
        self.f.close()

    def load_oneday_json(self, weekday: int):
        self.get_info()
        anime_jsons = json.load(open(self.json_path, 'r'))
        # 获取一天新番
        if weekday > 7 or weekday < 0:
            print('日期错误')
        else:
            self.weekday = int(weekday)
            self.anime_info = dict(anime_jsons[weekday])
            return self.anime_info

    def get_season_name(self):
        animes = {}
        aniems_info = {}
        for i in range(0, 7):
            info = self.load_oneday_json(i)
            for name in info['items']:
                if name['name_cn'] != '':
                    aniems_info['name_cn'] = name['name_cn']
                    aniems_info['bgm_id'] = name['id']
                    animes[name['name']] = aniems_info
                    aniems_info = {}
        self.f1 = open(self.animes_path, 'w')
        self.f1.write(json.dumps(animes, sort_keys=True, indent=4, separators=(',', ':')))
        self.f1.close()

    def get_score(self, bgm_id: str):
        bgm_id = str(bgm_id)
        self.detail = json.loads(
            requests.get(self.bangumi_api + '/subject/' + bgm_id, headers=self.headers, timeout=10).content)
        return self.detail['rating']['score']

    def get_score_bs4(self, bgm_id: str):
        bs4_url = self.bs4_url + '/subject/' + bgm_id
        page = requests.get(bs4_url, headers=config.real_headers, timeout=config.timeout).content
        soup = BeautifulSoup(page, 'lxml')
        bs4_bgm_score = soup.find('span', attrs={'class': 'number', 'property': 'v:average'}).string

        return bs4_bgm_score
