from fastapi import Request
from db import get_db

def get_current_user(request: Request):
    username = request.session.get("user")
    if not username:
        return None
    with get_db() as db:
        return db.execute(
            "SELECT * FROM players WHERE username = ?", (username,)
        ).fetchone()
