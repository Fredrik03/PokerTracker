import os
import sqlite3
from config import DATABASE_URL

# Whitelist your actual tables to prevent injection in PRAGMA calls
ALLOWED_TABLES = {
    "players",
    "auth_log",
    "games",
    "game_players",
    "admin_log",
    "potm_history",
}

def get_db():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    return conn

def column_exists(db, table: str, column: str) -> bool:
    # Ensure table is known
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table name: {table!r}")
    # PRAGMA table_info can’t parameterize the object, but whitelist defangs injections
    result = db.execute(f"PRAGMA table_info({table})").fetchall()
    return any(col["name"] == column for col in result)

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
            avatar_path TEXT,
            password_changed_at TEXT
        )""")

        # Auth log table for login attempts
        db.execute("""
        CREATE TABLE IF NOT EXISTS auth_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            ip_address TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )""")

        # Games table
        db.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            winner TEXT NOT NULL,
            amount INTEGER NOT NULL,
            rebuys INTEGER NOT NULL DEFAULT 0,
            buyin INTEGER DEFAULT 0
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

        # Admin audit log table with optional ip_address
        db.execute("""
        CREATE TABLE IF NOT EXISTS admin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            ip_address TEXT,
            timestamp TEXT NOT NULL
        )""")
        # Add ip_address column if missing
        if not column_exists(db, "admin_log", "ip_address"):
            db.execute("ALTER TABLE admin_log ADD COLUMN ip_address TEXT")

        # Player of the Month History table
        db.execute("""
        CREATE TABLE IF NOT EXISTS potm_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            username TEXT NOT NULL,
            avatar_path TEXT
        )""")

        # Indexes for performance
        db.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_log_username 
        ON auth_log(username)
        """)
        db.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_log_timestamp 
        ON auth_log(timestamp)
        """)
        db.execute("""
        CREATE INDEX IF NOT EXISTS idx_players_username 
        ON players(username)
        """)

        db.commit()