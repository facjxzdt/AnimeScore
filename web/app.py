from flask import Flask, render_template, request, make_response, redirect
from flask_sqlalchemy import SQLAlchemy
import data.config as config
import threading
import time
import schedule
import sql_add
import os

while True:
    if os.path.exists(config.work_dir + '/data/database.lock'):
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///'+config.work_dir+'/web/instance/anime.db'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db = SQLAlchemy(app)
        class Latest(db.Model):
            __tablename__ = 'latest'  # 指定数据库中的表名
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(250), nullable=False)
            name_cn = db.Column(db.String(250), nullable=True)
            bgm_id = db.Column(db.Integer, unique=True, nullable=False)
            poster = db.Column(db.String(250), nullable=True)
            mal_score = db.Column(db.Float, nullable=True)
            bgm_score = db.Column(db.Float, nullable=True)
            fm_score = db.Column(db.Float, nullable=True)
            ank_score = db.Column(db.Float, nullable=True)
            anl_score = db.Column(db.Float, nullable=True)
            score = db.Column(db.Float, nullable=True)
            time = db.Column(db.String(250), nullable=True)
        break
    else:
        time.sleep(5)

def deamon(interval=1):
    cease_continuous_run = threading.Event()
    class ScheduleThread(threading.Thread):
        @classmethod
        def run(cls):
            while not cease_continuous_run.is_set():
                schedule.run_pending()
                time.sleep(interval)
    continuous_thread = ScheduleThread()
    continuous_thread.start()
    return cease_continuous_run

@app.route('/reset_cookies')
def reset_cookies():
    resp = make_response(redirect('/'))
    # 设置cookie的默认值
    resp.set_cookie('bgm_weight', '0.5')
    resp.set_cookie('fm_weight', '0.3')
    resp.set_cookie('ank_weight', '0')
    resp.set_cookie('anl_weight', '0')
    resp.set_cookie('mal_weight', '0.2')
    return resp

@app.route('/')
def show_rankings():
    # 按 score 降序获取所有记录
    db.session.expire_all()
    animes = Latest.query.order_by(Latest.score.desc()).all()
    bgm_weight = float(request.cookies.get('bgm_weight', 0.5))
    fm_weight = float(request.cookies.get('fm_weight', 0.3))
    ank_weight = float(request.cookies.get('ank_weight', 0))
    anl_weight = float(request.cookies.get('anl_weight', 0))
    mal_weight = float(request.cookies.get('mal_weight', 0.2))

    for anime in animes:
        # 初始化加权分数为0
        weighted_score = 0

        # 为每个分数和相应的权重创建一个列表
        scores_and_weights = [
            (anime.bgm_score, bgm_weight),
            (anime.fm_score, fm_weight),
            (anime.ank_score, ank_weight),
            (anime.anl_score, anl_weight),
            (anime.mal_score, mal_weight)
        ]

        # 计算加权分数
        for score, weight in scores_and_weights:
            # 如果分数不是None且权重不为0，则加入到加权分数的计算中
            if score is not None and weight != 0:
                weighted_score += score * weight
            # 如果分数是None且权重不为0，则将加权分数设置为0，并跳出循环
            elif score is None and weight != 0:
                weighted_score = 0
                break

        # 将加权分数作为动画对象的一个临时属性
        setattr(anime, 'weighted_score', weighted_score)
        # 按加权分数降序排序
    animes_sorted = sorted(animes, key=lambda x: x.weighted_score, reverse=True)
    return render_template('ranking.html', animes=animes_sorted)

if __name__ == '__main__':
    while True:
        if os.path.exists(config.work_dir+'/data/database.lock'):
            schedule.every().day.at("19:45").do(sql_add.migrate)
            schedule.every().day.at("19:47").do(sql_add.store_data)
            _deamon = deamon()
            app.run(debug=True,host="0.0.0.0",port=5002)
            break
        else:
            time.sleep(5)
