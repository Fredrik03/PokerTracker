from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, date
import sqlite3

from config import BUYIN_DEFAULT, LOCAL_ZONE
from deps import get_current_user, generate_csrf, verify_csrf, tenant_required, get_tenant_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _log_action(conn, actor: str, action: str, target: str = None, ip: str = None, tenant_id: str = None):
    ts = datetime.now(tz=LOCAL_ZONE).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO admin_log (actor, action, target, ip_address, timestamp, tenant_id) VALUES (?, ?, ?, ?, ?, ?)",
        (actor, action, target, ip, ts, tenant_id)
    )
    conn.commit()


@router.get(
    "/admin",
    response_class=HTMLResponse,
    dependencies=[Depends(generate_csrf), Depends(tenant_required)]
)
def admin_panel(
    request: Request,
    user=Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_tenant_db),
    error: str = Query(default=None),
    msg: str = Query(default=None)
):
    if not user or user["is_admin"] != 1:
        return RedirectResponse("/dashboard", status_code=302)

    tid = request.state.tenant_id
    players = db.execute(
        "SELECT username, is_admin, balance FROM players WHERE tenant_id = ? ORDER BY username", (tid,)
    ).fetchall()
    all_players = db.execute(
        "SELECT username FROM players WHERE tenant_id = ? ORDER BY username", (tid,)
    ).fetchall()
    admin_logs = db.execute(
        "SELECT actor, action, target, ip_address, strftime('%Y-%m-%d %H:%M', datetime(timestamp)) AS timestamp"
        " FROM admin_log WHERE tenant_id = ? ORDER BY timestamp DESC LIMIT 50", (tid,)
    ).fetchall()
    auth_logs = db.execute(
        "SELECT username, success, ip_address, strftime('%Y-%m-%d %H:%M', datetime(timestamp)) AS timestamp"
        " FROM auth_log WHERE tenant_id = ? ORDER BY timestamp DESC LIMIT 50", (tid,)
    ).fetchall()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "players": players,
        "all_players": all_players,
        "logs": admin_logs,
        "auth_logs": auth_logs,
        "csrf_token": request.session.get("csrf_token"),
        "buyin": BUYIN_DEFAULT,
        "today": date.today().isoformat(),
        "msg": msg,
        "error": error
    })


@router.post("/toggle-admin", dependencies=[Depends(verify_csrf), Depends(tenant_required)])
def toggle_admin(
    request: Request,
    username: str = Form(...),
    user=Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_tenant_db)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)

    tid = request.state.tenant_id
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="Cannot change your own admin status")

    target = db.execute(
        "SELECT is_admin FROM players WHERE username = ? AND tenant_id = ?", (username, tid)
    ).fetchone()

    if target:
        new_status = 0 if target["is_admin"] else 1
        db.execute(
            "UPDATE players SET is_admin = ? WHERE username = ? AND tenant_id = ?",
            (new_status, username, tid)
        )
        _log_action(db, user["username"], f"toggle_admin={new_status}", username, request.client.host, tid)

    return RedirectResponse("/admin", status_code=302)


@router.post("/delete-user", dependencies=[Depends(verify_csrf), Depends(tenant_required)])
def delete_user(
    request: Request,
    username: str = Form(...),
    user=Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_tenant_db)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)

    tid = request.state.tenant_id
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    db.execute("DELETE FROM players WHERE username = ? AND tenant_id = ?", (username, tid))
    _log_action(db, user["username"], "delete_user", username, request.client.host, tid)

    return RedirectResponse("/admin", status_code=302)


@router.post("/create-user", response_class=HTMLResponse, dependencies=[Depends(verify_csrf), Depends(tenant_required)])
def create_user(
    request: Request,
    username: str = Form(...),
    is_admin: int = Form(0),
    user=Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_tenant_db)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)

    tid = request.state.tenant_id
    error = None
    msg = None
    try:
        db.execute(
            "INSERT INTO players (username, password, is_admin, must_set_password, balance, tenant_id)"
            " VALUES (?, ?, ?, 1, 0, ?)",
            (username, "", is_admin, tid)
        )
        _log_action(db, user["username"], "create_user", username, request.client.host, tid)
        msg = f"User '{username}' created."
    except sqlite3.IntegrityError:
        error = "Username already exists"

    players = db.execute(
        "SELECT username, is_admin, balance FROM players WHERE tenant_id = ? ORDER BY username", (tid,)
    ).fetchall()
    all_players = db.execute(
        "SELECT username FROM players WHERE tenant_id = ? ORDER BY username", (tid,)
    ).fetchall()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "players": players,
        "all_players": all_players,
        "logs": [],
        "auth_logs": [],
        "csrf_token": request.session.get("csrf_token"),
        "buyin": BUYIN_DEFAULT,
        "today": date.today().isoformat(),
        "msg": msg,
        "error": error
    })


@router.post("/reset-password", dependencies=[Depends(verify_csrf), Depends(tenant_required)])
def reset_password(
    request: Request,
    username: str = Form(...),
    user=Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_tenant_db)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)

    tid = request.state.tenant_id
    db.execute(
        "UPDATE players SET must_set_password = 1, password = '' WHERE username = ? AND tenant_id = ?",
        (username, tid)
    )
    _log_action(db, user["username"], "reset_password", username, request.client.host, tid)

    return RedirectResponse("/admin", status_code=302)


@router.post("/set-balance", dependencies=[Depends(verify_csrf), Depends(tenant_required)])
def set_balance(
    request: Request,
    username: str = Form(...),
    balance: int = Form(...),
    user=Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_tenant_db)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)

    tid = request.state.tenant_id
    db.execute(
        "UPDATE players SET balance = ? WHERE username = ? AND tenant_id = ?",
        (balance, username, tid)
    )
    _log_action(db, user["username"], f"set_balance={balance}", username, request.client.host, tid)

    return RedirectResponse("/admin", status_code=302)
