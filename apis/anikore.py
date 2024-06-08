import requests
import data.config as config

from bs4 import BeautifulSoup
from utils.logger import Log

log_ank = Log(__name__).getlog()


class Anikore:
    def __init__(self):
        self.url = "https://www.anikore.jp"

    def get_ani_id(self, anime: str):
        # 使用bgm获取到的日文原名进行精确匹配
        search_url = self.url + "/anime_title/" + anime
        log_ank.debug("正在向{}获取请求".format(search_url))
        page = requests.get(
            search_url, headers=config.real_headers, timeout=config.timeout
        ).content
        soup = BeautifulSoup(page, "lxml")
        log_ank.debug("正在解析网页")
        try:
            id_url = soup.find("div", attrs={"class": "l-searchPageRanking_unit"}).a[
                "href"
            ]
            # 提取ani_id
            ani_id = id_url[7 : len(id_url) - 1]
            log_ank.debug("{},anikore动画id获取成功".format(anime))
            return ani_id
        except:
            log_ank.debug("{},anikore动画id获取失败".format(anime))
            return "Error"

    def get_ani_score(self, ani_id: str):
        if ani_id != "Error":
            score_url = self.url + "/anime/" + ani_id
            log_ank.debug("正在向{}发送请求".format(score_url))
            page = requests.get(
                score_url, headers=config.real_headers, timeout=10
            ).content
            log_ank.debug("正在解析网页")
            soup = BeautifulSoup(page, "lxml")
            score = soup.find(
                "div",
                attrs={"class": "l-animeDetailHeader_pointAndButtonBlock_starBlock"},
            ).strong.string
            log_ank.debug("{},anikore动画评分获取成功".format(ani_id))
            return score
        return "None"
