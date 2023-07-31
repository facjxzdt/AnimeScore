import requests
import json

from data import config


class AniList:
    def __init__(self):
        self.api_url = 'https://graphql.anilist.co'

    def get_al_id(self, anime: str):
        query = '''
        query ($id: Int, $search: String) {
            Media (id: $id, search: $search,type: ANIME) {
                id
                title {
                    romaji
                }
                meanScore
            }
        }
        '''
        variables = {
            'search': anime
        }
        try:
            anl_id = requests.post(self.api_url, json={'query': query, 'variables': variables}, timeout=config.timeout)
            return json.loads(anl_id.content)['data']['Media']['id']
        except:
            return "Error"

    def get_al_score(self, anl_id: int):
        query = '''
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
        '''
        variables = {
            'id': anl_id
        }
        anl_score = requests.post(self.api_url, json={'query': query, 'variables': variables}, timeout=config.timeout)
        try:
            return (json.loads(anl_score.content)['data']['Media']['meanScore'] +
                    json.loads(anl_score.content)['data']['Media']['averageScore']) / 20
        except:
            try:
                return json.loads(anl_score.content)['data']['Media']['meanScore'] / 10
            except:
                return json.loads(anl_score.content)['data']['Media']['averageScore'] / 10
