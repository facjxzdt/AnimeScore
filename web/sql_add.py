from flask import Flask,request, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import inspect
import json
import os
import data.config as config


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///'+config.work_dir+'/web/instance/anime.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

file = open(config.work_dir+'/data/jsons/score_sorted.json')
json_data = json.load(file)

class AnimeBase(db.Model):
    __abstract__ = True  # 将AnimeBase设置为抽象基类
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
    time = db.Column(db.String(250), nullable=True)  # 使用字符串存储日期

def convert_score(score):
    """将分数从可能的'None'字符串或Python的None类型转换为None，否则转换为float类型"""
    if score == "None" or score is None:
        return None
    try:
        return float(score)
    except ValueError:
        # 如果转换失败（例如，score是不能转换为浮点数的字符串），返回None或者抛出错误
        return None
        # raise ValueError(f"无法将{score}转换为浮点数")


def get_anime_model(table_name="latest"):
    """
    动态创建Anime模型。
    默认情况下，如果没有提供表名，则使用'latest'。
    """
    class Anime(AnimeBase):
        __tablename__ = table_name
        __table_args__ = {'extend_existing': True}
    return Anime

def migrate_data():
    """
    将latest表的数据迁移到以当前日期命名的表中，并清空latest表。
    """
    LatestAnime = get_anime_model("latest")
    today_str = datetime.now().strftime("%Y_%m_%d")
    TodayAnime = get_anime_model(f"anime_{today_str}")

    # 使用inspect来检查今日表是否存在
    inspector = inspect(db.engine)
    if not today_str in [table_name for table_name in inspector.get_table_names()]:
        TodayAnime.__table__.create(db.engine)

    # 数据迁移
    latest_animes = LatestAnime.query.all()
    for anime in latest_animes:
        today_anime = TodayAnime(**{column.name: getattr(anime, column.name) for column in anime.__table__.columns})
        db.session.add(today_anime)
    db.session.commit()

    # 清空latest表
    db.session.query(LatestAnime).delete()
    db.session.commit()

def store_anime_data(data, table_name="latest"):
    """
    将动画数据存储到指定的表中。
    """
    AnimeModel = get_anime_model(table_name)
    for name, details in data.items():
        anime = AnimeModel(
            name=name,
            name_cn=details['name_cn'],
            bgm_id=details['bgm_id'],
            poster=details['poster'],
            mal_score=convert_score(details.get('mal_score')),
            bgm_score=convert_score(details.get('bgm_score')),
            fm_score=convert_score(details.get('fm_score')),
            ank_score=convert_score(details.get('ank_score')),
            anl_score=convert_score(details.get('anl_score')),
            score=convert_score(details.get('score')),
            time=json.dumps(details['time'])  # 将时间以JSON字符串的形式存储
        )
        db.session.add(anime)
    db.session.commit()

def migrate():
    db.session.expire_all()
    try:
        with app.app_context():
            migrate_data()
    except: pass
    return 0

def store_data():
    db.session.expire_all()
    with app.app_context():
        # 确保latest表存在
        get_anime_model("latest").__table__.create(db.engine, checkfirst=True)
        if os.path.exists(config.work_dir+'/web/instance/anime.db'):migrate_data()
        store_anime_data(json_data, "latest")
    return 0

if __name__ == '__main__':
    db.session.expire_all()
    with app.app_context():
        # 确保latest表存在
        get_anime_model("latest").__table__.create(db.engine, checkfirst=True)
        if os.path.exists(config.work_dir+'/web/instance/anime.db'):migrate_data()
        store_anime_data(json_data, "latest")