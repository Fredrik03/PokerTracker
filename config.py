import os
import secrets
from datetime import timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

BUYIN_DEFAULT   = 100
SESSION_SECRET  = os.getenv("SESSION_SECRET") or secrets.token_hex(32)
DATABASE_URL    = os.getenv("DATABASE_URL", "/app/data/poker.db")

# Time zone config
TIME_ZONE       = os.getenv("TIME_ZONE", "UTC")
if ZoneInfo:
    try:
        LOCAL_ZONE = ZoneInfo(TIME_ZONE)
    except Exception:
        # If the name is invalid or tzdata missing, fallback
        LOCAL_ZONE = timezone.utc
else:
    # zoneinfo not available
    LOCAL_ZONE = timezone.utc

# Bootstrap admin account:
ADMIN_USERNAME  = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD  = os.getenv("ADMIN_PASSWORD", "changeme")  # must be changed!
