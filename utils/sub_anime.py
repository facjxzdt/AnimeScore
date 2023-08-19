import json
from apis.bangumi import Bangumi
from utils.get_ids import get_single_id

bgm = Bangumi()
sub_json_path = '../data/jsons/sub.json'

def sub_animes(method: str,anime_name=None,bgm_id=None):
    try:
        anime_already_sub = json.load(open(sub_json_path,'r'))
    except:
        file = open(sub_json_path,'w')
        file.write('{}')
        file.close()
        anime_already_sub = json.load(open(sub_json_path,'r'))
    if method == 'name':
        anime_info = bgm.search_cli(anime_name)
        info = get_single_id(anime_info['id'])
        info['poster'] = anime_info['image']
    else:
        bgm_id = str(bgm_id)
        anime_info = bgm.get_anime_info(bgm_id)
        info = get_single_id(bgm_id)
        info['poster'] = anime_info['images']['large']
    info['name_cn'] = anime_info['name_cn']
    info['fm_id'] = info['fm_score']
    info.pop('fm_score')
    anime_already_sub[anime_info['name']] = info
    count =0
    for k in anime_already_sub.keys():
        if k != 'total':
            count += 1
    anime_already_sub['total'] = count
    f = open(sub_json_path,'w')
    f.write(json.dumps(anime_already_sub,sort_keys=True, indent=4, separators=(',', ':')))
    f.close()