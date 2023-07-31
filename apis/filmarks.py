import requests

from bs4 import BeautifulSoup
from data import config


class Filmarks:
    def __init__(self):
        self.url = 'https://filmarks.com'

    def get_fm_score(self, anime: str):
        search_url = self.url + '/search/animes?q=' + anime
        page = requests.get(search_url, headers=config.real_headers, timeout=config.timeout).content
        try:
            soup = BeautifulSoup(page, 'lxml')
            fm_score = soup.find('div', attrs={'class': 'c-rating__score'}).string

            return fm_score
        except:
            return "Error"
