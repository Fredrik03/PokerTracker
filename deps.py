import secrets
import sqlite3
from db import get_db
from fastapi import Request, HTTPException, Depends
from config import DATABASE_URL

# --- CSRF protection ---
def generate_csrf(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_hex(16)
        request.session["csrf_token"] = token
    return token

async def verify_csrf(request: Request) -> bool:
    form = await request.form()
    token = form.get("csrf_token")
    if not token or token != request.session.get("csrf_token"):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")
    return True

# --- Current user ---
def get_current_user(request: Request):
    username = request.session.get("user")
    tenant_id = getattr(request.state, "tenant_id", None)

    if not username or tenant_id is None:
        return None

    db = get_db()
    user = db.execute(
        "SELECT * FROM players WHERE username = ? AND tenant_id = ?",
        (username, tenant_id)
    ).fetchone()

    return user

# --- Tenant scoping ---
def tenant_required(request: Request) -> str:
    """
    Ensures this is a tenant subdomain and returns the tenant_id.
    Raises 403 if on the main domain.
    """
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(
            status_code=403,
            detail="This endpoint only works on a tenant subdomain"
        )
    return tid

# --- Per-request DB for tenants ---
def get_tenant_db(
    tenant_id: str = Depends(tenant_required),
):
    """
    Yields a fresh sqlite3.Connection for the current tenant
    and closes it when the request is done.
    """
    conn = sqlite3.connect(DATABASE_URL, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
