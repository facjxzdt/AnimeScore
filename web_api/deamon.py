import apis.bangumi
import meili_search
import utils.get_ids
import utils.get_score
import utils.json2csv
import utils.score
import utils.sub_anime

bgm = apis.bangumi.Bangumi()
meili = meili_search.Meilisearch()


def updata_score():
    bgm.get_season_name()
    utils.get_ids.get_ids()
    utils.get_score.get_score(method="air")
    utils.score.total_score("air")
    utils.json2csv.json2csv(method="air")


def meili_update():
    meili.add_anime2search(method="air")
