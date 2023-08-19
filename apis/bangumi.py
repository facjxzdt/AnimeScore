import requests
import json
import prettytable as pt

from bs4 import BeautifulSoup
from data import config
from utils.logger import Log

log_bgm = Log(__name__).getlog()

class Bangumi:
    def __init__(self):
        self.json_path = '../data/jsons/season.json'
        self.animes_path = '../data/jsons/animes.json'
        self.bangumi_api = "https://api.bgm.tv"
        self.bs4_url = 'https://bgm.tv'
        self.headers = {'user-agent': 'facjxzdt/autobangumi'}

    def get_info(self):
        # 获取bgm新番
        log_bgm.debug('向{}发送请求'.format(self.bangumi_api + '/calendar'))
        self.bgm_calendar = requests.get(self.bangumi_api + '/calendar', timeout=config.timeout).json()
        # 保存json
        self.f = open(self.json_path, 'w')
        self.f.write(json.dumps(self.bgm_calendar, sort_keys=True, indent=4, separators=(',', ':')))
        self.f.close()

    def load_oneday_json(self, weekday: int):
        log_bgm.info('获取星期{}的新番信息'.format(weekday+1))
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
        log_bgm.debug('获取整季新番')
        anime_count = 0
        animes = {}
        animes_info = {}
        for i in range(0, 7):
            info = self.load_oneday_json(i)
            for name in info['items']:
                if name['name_cn'] != '':
                    animes_info['name_cn'] = name['name_cn']
                    animes_info['bgm_id'] = name['id']
                    animes_info['poster'] = name['images']['large']
                    animes[name['name']] = animes_info
                    animes_info = {}
                    anime_count += 1
        animes['total'] = anime_count
        self.f1 = open(self.animes_path, 'w')
        self.f1.write(json.dumps(animes, sort_keys=True, indent=4, separators=(',', ':')))
        self.f1.close()

    def get_score(self, bgm_id: str):
        log_bgm.debug('正在获取{}的bgm评分'.format(bgm_id))
        bgm_id = str(bgm_id)
        self.detail = json.loads(
            requests.get(self.bangumi_api + '/subject/' + bgm_id, headers=self.headers, timeout=10).content)
        return self.detail['rating']['score']

    def get_score_bs4(self, bgm_id: str):
        log_bgm.debug('正在获取{}的bgm评分'.format(bgm_id))
        bs4_url = self.bs4_url + '/subject/' + bgm_id
        page = requests.get(bs4_url, headers=config.real_headers, timeout=config.timeout).content
        soup = BeautifulSoup(page, 'lxml')
        bs4_bgm_score = soup.find('span', attrs={'class': 'number', 'property': 'v:average'}).string

        return bs4_bgm_score

    def get_anime_info(self, bgm_id: str):
        log_bgm.info('正在获取{}的信息'.format(bgm_id))
        search_url = 'https://api.bgm.tv/v0/subjects/' + str(bgm_id)
        page = requests.get(search_url,headers=self.headers,timeout=config.timeout).content
        page = json.loads(page)
        return page

    def get_anime_name(self, bgm_id: str):
        info = self.get_anime_info(bgm_id)
        return info['name']

    def search_anime(self, anime_name: str):
        search_url = self.bangumi_api + '/v0/search/subjects'
        # 构造请求体
        post_body = {}
        filters = {}
        post_body['keyword'] = anime_name
        post_body['sort'] = 'rank'
        filters['type'] = [2]
        post_body['filter'] = filters
        post_body = json.dumps(post_body)
        # 发送post请求
        res = requests.post(search_url,headers=self.headers,data=post_body,timeout=config.timeout).content
        return json.loads(res)

    def search_cli(self, animes_name: str):
        search_dict = self.search_anime(animes_name)
        anime_table = pt.PrettyTable(["序号","中文名","日文原名","上映时间","评分","bgm_id"])
        anime_table.align = 'l'
        anime_table.align['bgm_id'] = 'r'
        anime_table.align['评分'] = 'm'
        anime_table.left_padding_width = 0
        num = 1
        index = 0
        for anime in search_dict['data']:
            anime = dict(anime)
            if anime['score'] != 0:
                anime['num'] = num
                search_dict['data'][index] = anime
                anime_table.add_row([anime['num'],anime['name_cn'],anime['name'],anime['date'],anime['score'],anime['id']])
                num += 1
            index += 1
        print(anime_table)
        choose = int(input('请输入序号: '))
        if 0 < choose < num:
            for anime in search_dict['data']:
                if 'num' in anime and anime['num'] == choose:
                    return anime