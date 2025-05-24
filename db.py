import os
import sqlite3
import uuid
from datetime import datetime
from config import DATABASE_URL, ADMIN_USERNAME, ADMIN_PASSWORD
from passlib.context import CryptContext

# Password hasher
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Whitelist actual tables to prevent injection in PRAGMA calls
ALLOWED_TABLES = {
    "users",
    "tenants",
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
    # PRAGMA table_info cannot parameterize the object, but whitelist defangs injections
    result = db.execute(f"PRAGMA table_info({table})").fetchall()
    return any(col[1] == column for col in result)

def init_db():
    # Ensure DB file and directory exist
    if not os.path.exists(DATABASE_URL):
        os.makedirs(os.path.dirname(DATABASE_URL), exist_ok=True)

    with get_db() as db:
        # 1. Global users table
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_superadmin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )""")

        # 2. Tenants table
        db.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            owner_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id)
        )""")

        # Tenant-scoped tables:
        # 3. Players
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
        if not column_exists(db, "players", "tenant_id"):
            db.execute("ALTER TABLE players ADD COLUMN tenant_id TEXT")

        # 4. Auth log
        db.execute("""
        CREATE TABLE IF NOT EXISTS auth_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            ip_address TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )""")
        if not column_exists(db, "auth_log", "tenant_id"):
            db.execute("ALTER TABLE auth_log ADD COLUMN tenant_id TEXT")

        # 5. Games
        db.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            winner TEXT NOT NULL,
            amount INTEGER NOT NULL,
            rebuys INTEGER NOT NULL DEFAULT 0,
            buyin INTEGER DEFAULT 0
        )""")
        if not column_exists(db, "games", "tenant_id"):
            db.execute("ALTER TABLE games ADD COLUMN tenant_id TEXT")

        # 6. GamePlayers
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
        if not column_exists(db, "game_players", "tenant_id"):
            db.execute("ALTER TABLE game_players ADD COLUMN tenant_id TEXT")

        # 7. Admin audit log
        db.execute("""
        CREATE TABLE IF NOT EXISTS admin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            ip_address TEXT,
            timestamp TEXT NOT NULL
        )""")
        if not column_exists(db, "admin_log", "ip_address"):
            db.execute("ALTER TABLE admin_log ADD COLUMN ip_address TEXT")
        if not column_exists(db, "admin_log", "tenant_id"):
            db.execute("ALTER TABLE admin_log ADD COLUMN tenant_id TEXT")

        # 8. Player of the Month History
        db.execute("""
        CREATE TABLE IF NOT EXISTS potm_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            username TEXT NOT NULL,
            avatar_path TEXT
        )""")
        if not column_exists(db, "potm_history", "tenant_id"):
            db.execute("ALTER TABLE potm_history ADD COLUMN tenant_id TEXT")

        # 9. Indexes for performance & tenant isolation
        db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_tenants_name ON tenants(name)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_players_tenant ON players(tenant_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_auth_log_tenant ON auth_log(tenant_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_games_tenant ON games(tenant_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_game_players_tenant ON game_players(tenant_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_admin_log_tenant ON admin_log(tenant_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_potm_history_tenant ON potm_history(tenant_id)")

        # Initialize admin accounts
        # 1. Create super admin if not exists
        super_exists = db.execute(
            "SELECT 1 FROM users WHERE is_superadmin = 1"
        ).fetchone()
        
        if not super_exists:
            user_id = str(uuid.uuid4())
            hashed_password = pwd_context.hash(ADMIN_PASSWORD)
            db.execute(
                "INSERT INTO users (id, username, password, is_superadmin, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, ADMIN_USERNAME, hashed_password, 1, datetime.utcnow().isoformat())
            )
            print(f"[startup] Created super admin user: {ADMIN_USERNAME}")

        # 2. Create tenant admin if not exists

        db.commit()
