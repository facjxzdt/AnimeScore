import httpx
import data.config as config
import re
from urllib.parse import quote

from bs4 import BeautifulSoup
from utils.logger import Log

log_ank = Log(__name__).getlog()


class Anikore:
    def __init__(self):
        self.url = "https://www.anikore.jp"
        self._score_cache = {}

    @staticmethod
    def _extract_score_from_unit(unit):
        # Search result page structure:
        # <div class="l-searchPageRanking_unit_mainBlock_starPoint">... <strong>4.5</strong>
        score_area = unit.find("div", attrs={"class": "l-searchPageRanking_unit_mainBlock_starPoint"})
        if score_area and score_area.find("strong"):
            raw = score_area.find("strong").get_text(strip=True)
            m = re.search(r"([0-4]\.\d|5\.0)", raw)
            if m:
                return m.group(1)
        return None

    def get_ani_id(self, anime: str):
        # 使用bgm获取到的日文原名进行精确匹配
        kw = quote(anime.strip())
        search_urls = [
            self.url + "/anime_title/" + kw,
            self.url + "/search/all/?q=" + kw,
        ]
        try:
            for search_url in search_urls:
                log_ank.debug("正在向{}获取请求".format(search_url))
                page = httpx.get(
                    search_url, headers=config.real_headers, timeout=config.timeout
                ).content
                soup = BeautifulSoup(page, "lxml")
                log_ank.debug("正在解析网页")

                # New/legacy list structure: find each ranking unit and parse id + score together.
                for unit in soup.find_all("div", attrs={"class": "l-searchPageRanking_unit"}):
                    a = unit.find("a", href=True)
                    if not a:
                        continue
                    href = a.get("href") or ""
                    m = re.search(r"/anime/(\d+)/", href)
                    if not m:
                        continue
                    ani_id = m.group(1)
                    score = self._extract_score_from_unit(unit)
                    if score is not None:
                        self._score_cache[ani_id] = score
                    log_ank.debug("{},anikore动画id获取成功".format(anime))
                    return ani_id

                # 旧版结构
                block = soup.find("div", attrs={"class": "l-searchPageRanking_unit"})
                if block and block.a and block.a.get("href"):
                    href = block.a.get("href")
                    m = re.search(r"/anime/(\d+)/", href)
                    if m:
                        ani_id = m.group(1)
                        log_ank.debug("{},anikore动画id获取成功".format(anime))
                        return ani_id

                # 兜底: 直接在全页面找第一个 /anime/{id}/ 链接
                for a in soup.find_all("a", href=True):
                    href = a.get("href") or ""
                    m = re.search(r"/anime/(\d+)/", href)
                    if m:
                        ani_id = m.group(1)
                        log_ank.debug("{},anikore动画id获取成功(兜底)".format(anime))
                        return ani_id
        except Exception:
            log_ank.debug("{},anikore动画id获取失败".format(anime))
        return "Error"

    async def get_ani_id_async(self, anime: str):
        kw = quote(anime.strip())
        search_urls = [
            self.url + "/anime_title/" + kw,
            self.url + "/search/all/?q=" + kw,
        ]
        try:
            async with httpx.AsyncClient(timeout=config.timeout) as client:
                for search_url in search_urls:
                    log_ank.debug("正在向{}获取请求(async)".format(search_url))
                    page = (await client.get(search_url, headers=config.real_headers)).content
                    soup = BeautifulSoup(page, "lxml")
                    log_ank.debug("正在解析网页(async)")

                    for unit in soup.find_all("div", attrs={"class": "l-searchPageRanking_unit"}):
                        a = unit.find("a", href=True)
                        if not a:
                            continue
                        href = a.get("href") or ""
                        m = re.search(r"/anime/(\d+)/", href)
                        if not m:
                            continue
                        ani_id = m.group(1)
                        score = self._extract_score_from_unit(unit)
                        if score is not None:
                            self._score_cache[ani_id] = score
                        log_ank.debug("{},anikore动画id获取成功(async)".format(anime))
                        return ani_id

                    block = soup.find("div", attrs={"class": "l-searchPageRanking_unit"})
                    if block and block.a and block.a.get("href"):
                        href = block.a.get("href")
                        m = re.search(r"/anime/(\d+)/", href)
                        if m:
                            ani_id = m.group(1)
                            log_ank.debug("{},anikore动画id获取成功(async)".format(anime))
                            return ani_id

                    for a in soup.find_all("a", href=True):
                        href = a.get("href") or ""
                        m = re.search(r"/anime/(\d+)/", href)
                        if m:
                            ani_id = m.group(1)
                            log_ank.debug("{},anikore动画id获取成功(兜底)(async)".format(anime))
                            return ani_id
        except Exception:
            log_ank.debug("{},anikore动画id获取失败(async)".format(anime))
        return "Error"

    def get_ani_score(self, ani_id: str):
        if ani_id != "Error":
            if ani_id in self._score_cache:
                return self._score_cache[ani_id]
            score_url = self.url + "/anime/" + ani_id
            log_ank.debug("正在向{}发送请求".format(score_url))
            page = httpx.get(
                score_url, headers=config.real_headers, timeout=10
            ).content
            log_ank.debug("正在解析网页")
            soup = BeautifulSoup(page, "lxml")
            # 旧版结构
            score_block = soup.find(
                "div",
                attrs={"class": "l-animeDetailHeader_pointAndButtonBlock_starBlock"},
            )
            if score_block and score_block.strong and score_block.strong.string:
                score = score_block.strong.string.strip()
                log_ank.debug("{},anikore动画评分获取成功".format(ani_id))
                return score

            # 兜底: 在文本中匹配一个 0.0-5.0 的评分
            text = soup.get_text(" ", strip=True)
            m = re.search(r"\b([0-4]\.\d|5\.0)\b", text)
            if m:
                score = m.group(1)
                log_ank.debug("{},anikore动画评分获取成功(兜底)".format(ani_id))
                return score
        return "None"

    async def get_ani_score_async(self, ani_id: str):
        if ani_id != "Error":
            if ani_id in self._score_cache:
                return self._score_cache[ani_id]
            score_url = self.url + "/anime/" + ani_id
            log_ank.debug("正在向{}发送请求(async)".format(score_url))
            async with httpx.AsyncClient(timeout=10) as client:
                page = (await client.get(score_url, headers=config.real_headers)).content
            log_ank.debug("正在解析网页(async)")
            soup = BeautifulSoup(page, "lxml")
            score_block = soup.find(
                "div",
                attrs={"class": "l-animeDetailHeader_pointAndButtonBlock_starBlock"},
            )
            if score_block and score_block.strong and score_block.strong.string:
                score = score_block.strong.string.strip()
                log_ank.debug("{},anikore动画评分获取成功(async)".format(ani_id))
                return score

            text = soup.get_text(" ", strip=True)
            m = re.search(r"\b([0-4]\.\d|5\.0)\b", text)
            if m:
                score = m.group(1)
                log_ank.debug("{},anikore动画评分获取成功(兜底)(async)".format(ani_id))
                return score
        return "None"
