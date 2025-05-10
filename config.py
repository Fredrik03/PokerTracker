import os, secrets

BUYIN_DEFAULT = 100
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_hex(32)
DATABASE_URL = "poker.db"
