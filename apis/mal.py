import requests

from bs4 import BeautifulSoup
from data import config

class MyAnimeList:
    def __init__(self):
        self.url = "https://myanimelist.net"

    def search_anime(self, anime: str):
        search_url = self.url + "/anime.php?q=" + anime + "&cat=anime"
        page = requests.get(search_url, headers=config.real_headers,timeout=config.timeout).content

        try:
            soup = BeautifulSoup(page, 'lxml')
            mal_id = \
                soup.find('div', attrs={'class': 'title'}).find('a', attrs={'class': 'hoverinfo_trigger fw-b fl-l'}).get(
                    'id')
            mal_id = mal_id[5:len(mal_id)]
            return mal_id
        except:
            return "Error"

    def get_anime_score(self, mal_id: str):
        score_url = self.url + "/anime/" + str(mal_id)
        page = requests.get(score_url,timeout=config.timeout).content

        soup = BeautifulSoup(page, 'lxml')
        mal_score = soup.find('div', attrs={'class': 'score-label'}).string

        return mal_score
