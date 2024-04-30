from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import data.config as config
import threading
import time
import schedule
import sql_add

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///anime.db'  # 指向您的数据库文件
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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

@app.route('/')
def show_rankings():
    # 按 score 降序获取所有记录
    animes = Latest.query.order_by(Latest.score.desc()).all()
    return render_template('ranking.html', animes=animes)

if __name__ == '__main__':
    schedule.every().day.at("19:45").do(sql_add.migrate)
    schedule.every().day.at("19:47").do(sql_add.store_data)
    _deamon = deamon()
    app.run(debug=False,host="0.0.0.0",port=5002)
