from flask import Flask, render_template
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

# 定义 Latest 模型，对应于数据库中的 latest 表

@app.route('/')
def show_rankings():
    # 按 score 降序获取所有记录
    animes = Latest.query.order_by(Latest.score.desc()).all()
    return render_template('ranking.html', animes=animes)

if __name__ == '__main__':
    while True:
        if os.path.exists(config.work_dir+'/data/database.lock'):
            schedule.every().day.at("19:45").do(sql_add.migrate)
            schedule.every().day.at("19:47").do(sql_add.store_data)
            _deamon = deamon()
            app.run(debug=False,host="0.0.0.0",port=5002)
            break
        else:
            time.sleep(5)
