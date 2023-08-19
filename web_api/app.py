from flask import Flask, request
import json

animes_path = '../data/jsons/score_sorted.json'

web = Flask(__name__)
def get_list():
    file = open('../data/jsons/score_sorted.json')
    scores = file
    return json.load(scores)


@web.route('/list')
def return_list():
    return get_list()

@web.route('/search/air/<id>', methods=['GET'])
def search_air_json(name):
    api = request.args.get('api')# ank anl bgm fm mal string类型

web.run()