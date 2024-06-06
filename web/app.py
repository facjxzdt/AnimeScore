import datetime
import os
import sqlite3
import threading
import time
from functools import wraps

import schedule
from flask import Flask, render_template, request, make_response, redirect, flash, url_for, session
from flask_sqlalchemy import SQLAlchemy

import data.config as config
from apis.anikore import Anikore
from apis.anilist import AniList
from apis.bangumi import Bangumi
from apis.filmarks import Filmarks
from apis.mal import MyAnimeList
from utils.get_score import get_single_score

mal = MyAnimeList()
ank = Anikore()
anl = AniList()
fm = Filmarks()
bgm = Bangumi()


def create_app():
    while True:
        if os.path.exists(config.work_dir + '/data/database.lock'):
            app = Flask(__name__)
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + config.work_dir + '/next/instance/anime.db'
            app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
            app.secret_key = config.key
            db = SQLAlchemy(app)
            _deamon = deamon()

            class Anime(db.Model):
                __tablename__ = 'score'
                title = db.Column(db.String(100), primary_key=True)
                name_cn = db.Column(db.String(100), nullable=True)
                bgm_id = db.Column(db.Integer, nullable=True)
                poster = db.Column(db.String(200), nullable=True)
                mal_score = db.Column(db.Float, nullable=True)
                bgm_score = db.Column(db.Float, nullable=True)
                fm_score = db.Column(db.Float, nullable=True)
                ank_score = db.Column(db.Float, nullable=True)
                anl_score = db.Column(db.Float, nullable=True)
                time = db.Column(db.String(250), nullable=True)

            class Anime_Info(db.Model):
                __tablename__ = 'anime'
                title = db.Column(db.String(100), primary_key=True)
                name_cn = db.Column(db.String(100), nullable=True)
                bgm_id = db.Column(db.Integer, nullable=True)
                poster = db.Column(db.String(200), nullable=True)
                mal_id = db.Column(db.Float, nullable=True)
                fm_id = db.Column(db.Float, nullable=True)
                ank_id = db.Column(db.Float, nullable=True)
                anl_id = db.Column(db.Float, nullable=True)

            break
        else:
            time.sleep(5)

    def _get_score():
        # 连接到SQLite数据库
        conn = sqlite3.connect(config.work_dir + '/next/instance/anime.db')
        cursor = conn.cursor()

        # 清空score表
        cursor.execute('DELETE FROM score')

        # 创建新的score表
        cursor.execute('''
                    CREATE TABLE IF NOT EXISTS score (
                        title TEXT,
                        name_cn TEXT,
                        bgm_id INTEGER,
                        poster TEXT,
                        mal_score REAL,
                        bgm_score REAL,
                        fm_score REAL,
                        ank_score REAL,
                        anl_score REAL,
                        time TEXT
                    )
                    ''')

        # 获取所有动画的相关数据
        cursor.execute('SELECT title, name_cn, bgm_id, poster, mal_id, ank_id, anl_id, fm_id FROM anime')
        animes = cursor.fetchall()

        # 遍历所有动画并计算分数
        for anime in animes:
            title, name_cn, bgm_id, poster, mal_id, ank_id, anl_id, fm_id = anime
            try:
                mal_score = mal.get_anime_score(mal_id)
            except:
                mal_score = None
            try:
                bgm_score = bgm.get_score(bgm_id)
            except:
                bgm_score = None
            try:
                ank_score = ank.get_ani_score(ank_id)
            except:
                ank_score = None
            try:
                anl_score = anl.get_al_score(anl_id)
            except:
                anl_score = None
            fm_score = 2 * float(fm_id) if fm_id and fm_id.replace('.', '',
                                                                   1).isdigit() else None  # 假设fm_score等于fm_id，如果fm_id是数值

            # 获取当前时间
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 将结果插入到score表中
            cursor.execute('''
                        INSERT INTO score (title, name_cn, bgm_id, poster, mal_score, bgm_score, fm_score, ank_score, anl_score, time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                title, name_cn, bgm_id, poster, mal_score, bgm_score, fm_score, ank_score, anl_score, current_time))

        # 提交更改并关闭连接
        conn.commit()
        conn.close()
        replace_na_with_none()

    schedule.every().day.at("19:30").do(_get_score)

    def replace_na_with_none(db_path=config.work_dir + '/next/instance/anime.db'):
        # 连接到SQLite数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取数据库中所有表的信息
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        # 遍历所有表和列，将N/A替换为None
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()

            for column in columns:
                column_name = column[1]
                # 更新表中N/A为None
                cursor.execute(f"UPDATE {table_name} SET {column_name} = NULL WHERE {column_name} = 'N/A'")

        # 提交更改并关闭连接
        conn.commit()
        conn.close()

    def remove_orphaned_scores():
        # 连接到SQLite数据库
        conn = sqlite3.connect(config.work_dir + '/next/instance/anime.db')
        cursor = conn.cursor()

        # 获取anime表中的所有title
        cursor.execute('SELECT title FROM anime')
        anime_titles = set(row[0] for row in cursor.fetchall())

        # 获取score表中的所有title
        cursor.execute('SELECT title FROM score')
        score_titles = set(row[0] for row in cursor.fetchall())

        # 找出存在于score表中但不存在于anime表中的title
        orphaned_titles = score_titles - anime_titles

        # 删除这些孤立的记录
        for title in orphaned_titles:
            cursor.execute('DELETE FROM score WHERE title = ?', (title,))

        # 提交更改并关闭连接
        conn.commit()
        conn.close()

    def update_single_score(title):
        anime_info = Anime_Info.query.get(title)
        anime = Anime.query.get(title)
        if not anime_info:
            flash(f'Anime with title {title} not found.')
            return

        try:
            mal_score = mal.get_anime_score(anime_info.mal_id)
        except:
            mal_score = None
        try:
            bgm_score = bgm.get_score(anime_info.bgm_id)
        except:
            bgm_score = None
        try:
            ank_score = ank.get_ani_score(anime_info.ank_id)
        except:
            ank_score = None
        try:
            anl_score = anl.get_al_score(anime_info.anl_id)
        except:
            anl_score = None
        fm_score = fm.get_fm_score(anime_info.title)

        anime.mal_score = mal_score
        anime.bgm_score = bgm_score
        anime.fm_score = fm_score
        anime.ank_score = ank_score
        anime.anl_score = anl_score
        anime.time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db.session.commit()
        flash(f'Scores for {title} updated successfully.')

    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session:
                return redirect(url_for('login'))
            return f(*args, **kwargs)

        return decorated_function

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
        db.session.expire_all()
        animes = Anime.query.all()
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
            setattr(anime, 'weighted_score', format(weighted_score, '.3f'))
            # 按加权分数降序排序
        animes_sorted = sorted(animes, key=lambda x: x.weighted_score, reverse=True)
        return render_template('ranking.html', animes=animes_sorted)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        if request.method == 'POST':
            if request.form['password'] != config.key:
                error = 'Invalid password. Please try again.'
            else:
                session['logged_in'] = True
                flash('You were successfully logged in')
                return redirect(url_for('show_rankings'))
        return render_template('login.html', error=error)

    @app.route('/logout')
    def logout():
        session.pop('logged_in', None)
        flash('You were successfully logged out')
        return redirect(url_for('show_rankings'))

    @app.route('/update_single_score/<title>', methods=['POST'])
    @login_required
    def update_single_anime_score(title):
        update_single_score(title)
        return redirect(url_for('show_rankings'))

    @app.route('/get_score', methods=['POST'])
    @login_required
    def get_score():
        _get_score()
        flash('All anime scores updated successfully.')
        return redirect(url_for('show_rankings'))

    @app.route('/search', methods=['POST'])
    def search():
        # 从请求体中获取BGM ID
        bgm_id = str(request.json.get('bgm_id'))
        anime = get_single_score(bgm_id)
        if anime:
            # 如果找到了，返回动画信息的JSON
            return anime
        else:
            # 如果没找到，返回错误信息
            return {"error": "Anime not found"}, 404

    return app


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


if __name__ == '__main__':
    app = create_app()
    app.run(debug=False, host="0.0.0.0", port=5002)
