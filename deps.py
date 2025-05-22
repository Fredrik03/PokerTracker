from fastapi import Request, HTTPException, Depends
from db import get_db
import secrets

# CSRF constants
CSRF_SESSION_KEY = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"

async def generate_csrf(request: Request) -> str:
    """
    Ensure there's a CSRF token in the session and return it.
    Use this in GET routes (via Depends) to inject a fresh token into templates.
    """
    if CSRF_SESSION_KEY not in request.session:
        request.session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
    return request.session[CSRF_SESSION_KEY]

async def verify_csrf(request: Request):
    """
    Validate that the token sent in the form or header matches the one in session.
    Attach as a dependency on all POST handlers.
    """
    form = await request.form()
    token = form.get(CSRF_FORM_FIELD)
    # Fallback to header
    if not token:
        token = request.headers.get(CSRF_HEADER)
    if not token or token != request.session.get(CSRF_SESSION_KEY):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")


def get_current_user(request: Request):
    username = request.session.get("user")
    if not username:
        return None
    with get_db() as db:
        return db.execute(
            "SELECT * FROM players WHERE username = ?", (username,)
        ).fetchone()
