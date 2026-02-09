import apis.bangumi
import utils.get_ids
import utils.get_score
import utils.json2csv
import utils.score
import utils.sub_anime

bgm = apis.bangumi.Bangumi()


def updata_score():
    bgm.get_season_name()
    utils.get_ids.get_ids()
    utils.get_score.get_score(method="air")
    utils.score.total_score("air")
    utils.json2csv.json2csv(method="air")
    try:
        from web_api.api_v1.deps import clear_cache
        clear_cache()
    except Exception:
        pass
