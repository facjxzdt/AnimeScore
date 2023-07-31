import requests
import data.config as config

from bs4 import BeautifulSoup


class Anikore:
    def __init__(self):
        self.url = 'https://www.anikore.jp'

    def get_ani_id(self, anime: str):
        # 使用bgm获取到的日文原名进行精确匹配
        search_url = self.url + '/anime_title/' + anime
        page = requests.get(search_url, headers=config.real_headers, timeout=config.timeout).content
        soup = BeautifulSoup(page, 'lxml')
        try:
            id_url = soup.find('div', attrs={'class': 'l-searchPageRanking_unit'}).a['href']

            # 提取ani_id
            ani_id = id_url[7:len(id_url) - 1]
            return ani_id
        except:
            return "Error"

    def get_ani_score(self, ani_id: str):
        score_url = self.url + '/anime/' + ani_id
        page = requests.get(score_url, headers=config.real_headers, timeout=10).content
        soup = BeautifulSoup(page, 'lxml')
        score = soup.find('div', attrs={'class': 'l-animeDetailHeader_pointAndButtonBlock_starBlock'}).strong.string

        return score
