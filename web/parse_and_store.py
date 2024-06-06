# /mnt/data/parse_and_store.py
import json
import sqlite3
import data.config

def create_database():
    conn = sqlite3.connect('animes.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS animes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            ank_id TEXT,
            anl_id TEXT,
            bgm_id TEXT,
            fm_id TEXT,
            mal_id TEXT,
            name_cn TEXT,
            poster TEXT
        )
    ''')
    conn.commit()
    conn.close()

def insert_data(data):
    conn = sqlite3.connect('animes.db')
    cursor = conn.cursor()
    for name, info in data.items():
        if name == "total":
            continue
        cursor.execute('''
            INSERT INTO animes (name, ank_id, anl_id, bgm_id, fm_id, mal_id, name_cn, poster)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, info['ank_id'], info['anl_id'], info['bgm_id'], info['fm_id'], info['mal_id'], info['name_cn'], info['poster']))
    conn.commit()
    conn.close()

with open(data.config.work_dir+'/data/jsons/animes.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

create_database()
insert_data(data)
