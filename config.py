# config.py
import os, secrets

BUYIN_DEFAULT   = 100
SESSION_SECRET  = os.getenv("SESSION_SECRET") or secrets.token_hex(32)
DATABASE_URL    = "data/poker.db"

# Bootstrap admin account:
ADMIN_USERNAME  = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD  = os.getenv("ADMIN_PASSWORD", "changeme")  # must be changed!
