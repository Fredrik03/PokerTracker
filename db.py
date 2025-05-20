import os
import sqlite3
from config import DATABASE_URL

def get_db():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DATABASE_URL):
        os.makedirs(os.path.dirname(DATABASE_URL), exist_ok=True)
        with get_db() as db:
            # Players table
            db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                balance INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                must_set_password INTEGER DEFAULT 0,
                avatar_path TEXT
            )""")

            # Games table
            db.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                winner TEXT NOT NULL,
                amount INTEGER NOT NULL,
                rebuys INTEGER NOT NULL DEFAULT 0
            )""")

            # GamePlayers table
            db.execute("""
            CREATE TABLE IF NOT EXISTS game_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                buyin INTEGER NOT NULL,
                rebuys INTEGER NOT NULL,
                cashout INTEGER NOT NULL,
                net INTEGER NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games(id),
                FOREIGN KEY (username) REFERENCES players(username)
            )""")

            db.commit()
