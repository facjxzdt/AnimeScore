import httpx

from bs4 import BeautifulSoup
from data import config
from utils.logger import Log

log_fm = Log(__name__).getlog()


class Filmarks:
    def __init__(self):
        self.url = "https://filmarks.com"

    def get_fm_score(self, anime: str):
        log_fm.debug("正在获取{}的fm分数".format(anime))
        search_url = self.url + "/search/animes?q=" + anime
        log_fm.debug("正在向{}发送请求".format(search_url))
        page = httpx.get(
            search_url, headers=config.real_headers, timeout=config.timeout
        ).content
        try:
            log_fm.debug("正在解析页面")
            soup = BeautifulSoup(page, "lxml")
            fm_score = soup.find("div", attrs={"class": "c-rating__score"}).string

            return fm_score
        except:
            log_fm.error("{}的fm评分查询失败".format(anime))
            return "Error"

    async def get_fm_score_async(self, anime: str):
        log_fm.debug("正在获取{}的fm分数(async)".format(anime))
        search_url = self.url + "/search/animes?q=" + anime
        log_fm.debug("正在向{}发送请求(async)".format(search_url))
        async with httpx.AsyncClient(timeout=config.timeout) as client:
            page = (await client.get(search_url, headers=config.real_headers)).content
        try:
            log_fm.debug("正在解析页面(async)")
            soup = BeautifulSoup(page, "lxml")
            fm_score = soup.find("div", attrs={"class": "c-rating__score"}).string
            return fm_score
        except:
            log_fm.error("{}的fm评分查询失败(async)".format(anime))
            return "Error"
