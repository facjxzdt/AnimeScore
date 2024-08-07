import apis.bangumi
import utils.get_ids
import utils.get_score
import utils.score
import utils.json2csv
import utils.sub_anime

print("正在获取新番信息")
bgm = apis.bangumi.Bangumi()
bgm.get_season_name()

print("正在获取动画id")
utils.get_ids.get_ids()
print("正在获取动画评分")
utils.get_score.get_score(method="air")
utils.score.total_score("air")
print("存储为csv...")
utils.json2csv.json2csv(method="air")
print("完成")
