# db.py
import sqlite3
from config import DATABASE_URL

def get_db():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            balance INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            must_set_password INTEGER DEFAULT 0
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            winner TEXT NOT NULL,
            amount INTEGER NOT NULL
        )""")
        db.commit()
