import httpx

from bs4 import BeautifulSoup
from data import config
from utils.logger import Log

log_mal = Log(__name__).getlog()


class MyAnimeList:
    def __init__(self):
        self.url = "https://myanimelist.net"

    def search_anime(self, anime: str):
        log_mal.debug("正在获取{}的mal_id".format(anime))
        search_url = self.url + "/anime.php?q=" + anime + "&cat=anime"
        log_mal.debug("正在向{}发送请求".format(search_url))
        page = httpx.get(
            search_url, headers=config.real_headers, timeout=config.timeout
        ).content

        try:
            soup = BeautifulSoup(page, "lxml")
            mal_id = (
                soup.find("div", attrs={"class": "title"})
                .find("a", attrs={"class": "hoverinfo_trigger fw-b fl-l"})
                .get("id")
            )
            mal_id = mal_id[5 : len(mal_id)]
            log_mal.debug("获取{}的mal_id成功".format(anime))
            return mal_id
        except:
            log_mal.debug("获取{}的mal_id失败".format(anime))
            return "Error"

    async def search_anime_async(self, anime: str):
        log_mal.debug("正在获取{}的mal_id(async)".format(anime))
        search_url = self.url + "/anime.php?q=" + anime + "&cat=anime"
        log_mal.debug("正在向{}发送请求(async)".format(search_url))
        async with httpx.AsyncClient(timeout=config.timeout) as client:
            page = (await client.get(search_url, headers=config.real_headers)).content

        try:
            soup = BeautifulSoup(page, "lxml")
            mal_id = (
                soup.find("div", attrs={"class": "title"})
                .find("a", attrs={"class": "hoverinfo_trigger fw-b fl-l"})
                .get("id")
            )
            mal_id = mal_id[5 : len(mal_id)]
            log_mal.debug("获取{}的mal_id成功(async)".format(anime))
            return mal_id
        except:
            log_mal.debug("获取{}的mal_id失败(async)".format(anime))
            return "Error"

    def get_anime_score(self, mal_id: str):
        if mal_id != "Error":
            log_mal.debug("正在获取{}的mal评分".format(mal_id))
            score_url = self.url + "/anime/" + str(mal_id)
            page = httpx.get(score_url, timeout=config.timeout).content

            soup = BeautifulSoup(page, "lxml")
            mal_score = soup.find("div", attrs={"class": "score-label"}).string

            return mal_score
        return "None"

    async def get_anime_score_async(self, mal_id: str):
        if mal_id != "Error":
            log_mal.debug("正在获取{}的mal评分(async)".format(mal_id))
            score_url = self.url + "/anime/" + str(mal_id)
            async with httpx.AsyncClient(timeout=config.timeout) as client:
                page = (await client.get(score_url)).content

            soup = BeautifulSoup(page, "lxml")
            mal_score = soup.find("div", attrs={"class": "score-label"}).string
            return mal_score
        return "None"
