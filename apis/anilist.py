import requests
import json

from data import config
from utils.logger import Log

log_anl = Log(__name__).getlog()


class AniList:
    def __init__(self):
        self.api_url = "https://graphql.anilist.co"

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
            anl_id = requests.post(
                self.api_url,
                json={"query": query, "variables": variables},
                timeout=config.timeout,
            )
            return json.loads(anl_id.content)["data"]["Media"]["id"]
        except:
            log_anl.debug("获取{}的anl_id失败".format(anime))
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
            anl_score = requests.post(
                self.api_url,
                json={"query": query, "variables": variables},
                timeout=config.timeout,
            )
            log_anl.debug("正在获取{}的anl评分".format(anl_id))
            try:
                return (
                    json.loads(anl_score.content)["data"]["Media"]["meanScore"]
                    + json.loads(anl_score.content)["data"]["Media"]["averageScore"]
                ) / 20
            except:
                try:
                    return (
                        json.loads(anl_score.content)["data"]["Media"]["meanScore"] / 10
                    )
                except:
                    return (
                        json.loads(anl_score.content)["data"]["Media"]["averageScore"]
                        / 10
                    )
        return "None"
