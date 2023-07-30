import apis.anikore,apis.anilist,apis.bangumi,apis.filmarks,apis.mal
import utils.get_ids,utils.get_score,utils.json2csv,utils.score

print('正在获取新番信息')
bgm = apis.bangumi.Bangumi()
bgm.get_season_name()
print('正在获取动画id')
utils.get_ids.get_ids()
print('正在获取动画评分')
utils.get_score.get_score()
utils.score.total_score()
print('存储为csv...')
utils.json2csv.json2csv()
print('完成')