from flask import Flask, request, flash, session, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import json
import data.config

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///anime.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
app.secret_key = data.config.key
bcrypt = Bcrypt(app)

# 定义数据库模型
class Anime(db.Model):
    title = db.Column(db.String(100), primary_key=True)
    ank_id = db.Column(db.String(50), nullable=True)
    anl_id = db.Column(db.Integer, nullable=True)
    bgm_id = db.Column(db.Integer, nullable=True)
    fm_id = db.Column(db.String(10), nullable=True)
    mal_id = db.Column(db.String(50), nullable=True)
    name_cn = db.Column(db.String(100), nullable=True)
    poster = db.Column(db.String(200), nullable=True)
    skip = db.Column(db.Boolean, default=False)  # 新增字段，表示是否跳过


# 主页，显示所有数据
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    animes = Anime.query.all()
    return render_template('index.html', animes=animes)

hashed_password = bcrypt.generate_password_hash(data.config.key).decode('utf-8')

@app.route('/sync_animes', methods=['POST'])
def sync_animes():
    add_animes_from_json(data.config.work_dir + '/data/jsons/animes.json')
    flash('Anime data synchronized successfully.')
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        if bcrypt.check_password_hash(hashed_password, password):
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            flash('Invalid password, please try again.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# 添加新番条目
@app.route('/add', methods=['POST'])
def add_anime():
    data = request.form
    title = data['title']

    # 检查是否已经存在具有相同标题的记录
    existing_anime = Anime.query.get(title)
    if existing_anime:
        return redirect(url_for('index'))  # 如果存在，则跳过插入

    new_anime = Anime(
        title=title,
        ank_id=data.get('ank_id', None) if data.get('ank_id') != "Error" else None,
        anl_id=int(data['anl_id']) if data.get('anl_id') and data.get('anl_id') != "Error" else None,
        bgm_id=int(data['bgm_id']) if data.get('bgm_id') and data.get('bgm_id') != "Error" else None,
        fm_id=data.get('fm_id', None) if data.get('fm_id') != "Error" else None,
        mal_id=data.get('mal_id', None) if data.get('mal_id') != "Error" else None,
        name_cn=data.get('name_cn', None) if data.get('name_cn') != "Error" else None,
        poster=data.get('poster', None) if data.get('poster') != "Error" else None,
        skip=False
    )
    db.session.add(new_anime)
    db.session.commit()
    return redirect(url_for('index'))


# 更新新番条目
@app.route('/update/<title>', methods=['GET', 'POST'])
def update_anime(title):
    anime = Anime.query.get(title)
    if request.method == 'POST':
        if anime:
            data = request.form
            anime.title = data.get('title', anime.title)
            anime.ank_id = data.get('ank_id', None) if data.get('ank_id') != "Error" else None
            anime.anl_id = int(data['anl_id']) if data.get('anl_id') and data.get('anl_id') != "Error" else None
            anime.bgm_id = int(data['bgm_id']) if data.get('bgm_id') and data.get('bgm_id') != "Error" else None
            anime.fm_id = data.get('fm_id', None) if data.get('fm_id') != "Error" else None
            anime.mal_id = data.get('mal_id', None) if data.get('mal_id') != "Error" else None
            anime.name_cn = data.get('name_cn', None) if data.get('name_cn') != "Error" else None
            anime.poster = data.get('poster', None) if data.get('poster') != "Error" else None
            anime.skip = data.get('skip') == 'True'  # 更新skip字段
            db.session.commit()
        return redirect(url_for('index'))
    return render_template('update.html', anime=anime)


# 删除新番条目
@app.route('/delete/<title>', methods=['POST'])
def delete_anime(title):
    anime = Anime.query.get(title)
    if anime:
        db.session.delete(anime)
        db.session.commit()
    return redirect(url_for('index'))

def add_animes_from_json(json_file_path):
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    with app.app_context():
        # 获取数据库中的所有条目
        existing_animes = Anime.query.all()
        existing_titles = {anime.title for anime in existing_animes}

        # 获取 JSON 文件中的条目
        json_titles = set(data.keys())

        # 找出需要删除的条目
        titles_to_delete = existing_titles - json_titles

        # 删除数据库中不在 JSON 文件中的条目
        for title in titles_to_delete:
            anime_to_delete = Anime.query.get(title)
            if anime_to_delete:
                db.session.delete(anime_to_delete)

        # 添加或更新 JSON 文件中的条目
        for title, details in data.items():
            if not isinstance(details, dict):
                continue  # 跳过非字典项，如 "total"

            ank_id = details.get('ank_id')
            if ank_id == "Error":
                ank_id = None

            anl_id = details.get('anl_id')
            if anl_id == "Error":
                anl_id = None
            elif isinstance(anl_id, str) and anl_id.isdigit():
                anl_id = int(anl_id)

            bgm_id = details.get('bgm_id')
            if bgm_id == "Error":
                bgm_id = None
            elif isinstance(bgm_id, str) and bgm_id.isdigit():
                bgm_id = int(bgm_id)

            fm_id = details.get('fm_id')
            if fm_id == "Error":
                fm_id = None

            mal_id = details.get('mal_id')
            if mal_id == "Error":
                mal_id = None

            name_cn = details.get('name_cn')
            if name_cn == "Error":
                name_cn = None

            poster = details.get('poster')
            if poster == "Error":
                poster = None

            # 检查是否已经存在条目
            existing_anime = Anime.query.get(title)
            if existing_anime:
                if existing_anime.skip:
                    continue  # 跳过已经标记为skip的条目
                else:
                    # 更新现有条目
                    existing_anime.ank_id = ank_id
                    existing_anime.anl_id = anl_id
                    existing_anime.bgm_id = bgm_id
                    existing_anime.fm_id = fm_id
                    existing_anime.mal_id = mal_id
                    existing_anime.name_cn = name_cn
                    existing_anime.poster = poster
            else:
                # 插入新条目
                new_anime = Anime(
                    title=title,
                    ank_id=ank_id,
                    anl_id=anl_id,
                    bgm_id=bgm_id,
                    fm_id=fm_id,
                    mal_id=mal_id,
                    name_cn=name_cn,
                    poster=poster,
                    skip=False
                )
                db.session.add(new_anime)
        db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        add_animes_from_json(data.config.work_dir + '/data/jsons/animes.json')
        db.create_all()
    app.run(debug=False)
