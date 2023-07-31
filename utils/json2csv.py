import csv
import json

scores_path = '../data/score_sorted.json'
csv_path = '../data/score.csv'


def json2csv():
    scores = json.load(open(scores_path, 'r'))
    line = []
    first_line = ['name', 'name_cn', 'bgm_id', 'bgm_score', 'fm_score', 'mal_score', 'ank_score', 'anl_score', 'score']
    with open(csv_path, 'w', newline='', encoding='gb18030') as csvfile:
        writer = csv.writer(csvfile, dialect=("excel"))
        writer.writerow(first_line)
        for v in scores.values():
            for i in range(0, 9):
                line.append(v[first_line[i]])
            writer.writerow(line)
            line = []
