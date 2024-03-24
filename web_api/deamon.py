import apis.bangumi
import utils.get_ids, utils.get_score, utils.score, utils.json2csv,utils.sub_anime
import schedule
import meili_search

bgm = apis.bangumi.Bangumi()
meili = meili_search.Meilisearch()

def updata_score():
    bgm.get_season_name()
    utils.get_ids.get_ids()
    utils.get_score.get_score(method='air')
    utils.score.total_score('air')
    utils.json2csv.json2csv(method='air')

def meili_update():
    meili.add_anime2search(method='air')