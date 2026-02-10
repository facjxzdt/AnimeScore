import json
import httpx

from data import config
from utils.logger import Log

log_anl = Log(__name__).getlog()


class AniList:
    def __init__(self):
        self.api_url = "https://graphql.anilist.co"
        self._headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def _post(self, query: str, variables: dict) -> dict:
        res = httpx.post(
            self.api_url,
            json={"query": query, "variables": variables},
            headers=self._headers,
            timeout=config.timeout,
        )
        res.raise_for_status()
        return res.json()

    async def _apost(self, query: str, variables: dict) -> dict:
        async with httpx.AsyncClient(timeout=config.timeout) as client:
            res = await client.post(
                self.api_url,
                json={"query": query, "variables": variables},
                headers=self._headers,
            )
            res.raise_for_status()
            return res.json()

    def get_al_id(self, anime: str):
        query = """
        query ($id: Int, $search: String) {
            Media (id: $id, search: $search,type: ANIME) {
                id
                title {
                    romaji
                }
                meanScore
            }
        }
        """
        variables = {"search": anime}
        try:
            log_anl.debug("正在获取{}的anl_id".format(anime))
            data = self._post(query, variables)
            return data["data"]["Media"]["id"]
        except:
            log_anl.debug("获取{}的anl_id失败".format(anime))
            return "Error"

    async def get_al_id_async(self, anime: str):
        query = """
        query ($id: Int, $search: String) {
            Media (id: $id, search: $search,type: ANIME) {
                id
                title {
                    romaji
                }
                meanScore
            }
        }
        """
        variables = {"search": anime}
        try:
            log_anl.debug("正在获取{}的anl_id(async)".format(anime))
            data = await self._apost(query, variables)
            return data["data"]["Media"]["id"]
        except:
            log_anl.debug("获取{}的anl_id失败(async)".format(anime))
            return "Error"

    def get_al_score(self, anl_id: str):
        if anl_id != "Error":
            query = """
            query ($id: Int) {
              Media (id: $id, type: ANIME) {
                id
                title {
                  romaji
                  english
                  native
                }
                meanScore
                averageScore
              }
            }
            """
            variables = {"id": int(anl_id)}
            log_anl.debug("正在获取{}的anl评分".format(anl_id))
            try:
                payload = self._post(query, variables)
                media = payload.get("data", {}).get("Media", {})
                mean_score = media.get("meanScore")
                avg_score = media.get("averageScore")
                if mean_score is not None and avg_score is not None:
                    return (mean_score + avg_score) / 20
                if mean_score is not None:
                    return mean_score / 10
                if avg_score is not None:
                    return avg_score / 10
            except:
                return "None"
        return "None"

    async def get_al_score_async(self, anl_id: str):
        if anl_id != "Error":
            query = """
            query ($id: Int) {
              Media (id: $id, type: ANIME) {
                id
                title {
                  romaji
                  english
                  native
                }
                meanScore
                averageScore
              }
            }
            """
            variables = {"id": int(anl_id)}
            log_anl.debug("正在获取{}的anl评分(async)".format(anl_id))
            try:
                payload = await self._apost(query, variables)
                media = payload.get("data", {}).get("Media", {})
                mean_score = media.get("meanScore")
                avg_score = media.get("averageScore")
                if mean_score is not None and avg_score is not None:
                    return (mean_score + avg_score) / 20
                if mean_score is not None:
                    return mean_score / 10
                if avg_score is not None:
                    return avg_score / 10
            except:
                return "None"
        return "None"
