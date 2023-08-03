from apis.bangumi import Bangumi
from utils.score import count_single_score
from utils.get_score import get_single_score

bgm = Bangumi()
animes_id = []
id = ""

print('请输入你想查询的bgm id，以end结束')

while True:
    id = input()
    if id != 'end':
        animes_id.append(str(id))
    else:
        break

for id in animes_id:
    print(count_single_score(get_single_score(id)))