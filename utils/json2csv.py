import csv
import json

from utils.logger import Log

scores_path = '../data/jsons/score_sorted.json'
csv_path = '../data/score.csv'

log_json = Log(__name__).getlog()

def json2csv():
    log_json.info('写入csv')
    scores = json.load(open(scores_path, 'r'))
    line = []
    first_line = ['name', 'name_cn', 'bgm_id', 'bgm_score', 'fm_score', 'mal_score', 'ank_score', 'anl_score', 'score', 'time']
    with open(csv_path, 'w', newline='', encoding='gb18030') as csvfile:
        writer = csv.writer(csvfile, dialect=("excel"))
        writer.writerow(first_line)
        for v in scores.values():
            for i in range(0, len(first_line)):
                line.append(v[first_line[i]])
            writer.writerow(line)
            line = []