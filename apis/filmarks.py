import requests

from bs4 import BeautifulSoup
from data import config
from utils.logger import Log

log_fm = Log(__name__).getlog()

class Filmarks:
    def __init__(self):
        self.url = 'https://filmarks.com'

    def get_fm_score(self, anime: str):
        log_fm.debug('正在获取{}的fm分数'.format(anime))
        search_url = self.url + '/search/animes?q=' + anime
        log_fm.debug('正在向{}发送请求'.format(search_url))
        page = requests.get(search_url, headers=config.real_headers, timeout=config.timeout).content
        try:
            log_fm.debug('正在解析页面')
            soup = BeautifulSoup(page, 'lxml')
            fm_score = soup.find('div', attrs={'class': 'c-rating__score'}).string

            return fm_score
        except:
            log_fm.error('{}的fm评分查询失败'.format(anime))
            return "Error"
