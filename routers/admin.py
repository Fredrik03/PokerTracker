from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import sqlite3

from deps import get_current_user, generate_csrf, verify_csrf
from db import get_db
from config import LOCAL_ZONE

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/admin", response_class=HTMLResponse, dependencies=[Depends(generate_csrf)])
def admin_panel(request: Request, user=Depends(get_current_user)):
    if not user or user["is_admin"] != 1:
        return RedirectResponse("/dashboard", status_code=302)

    with get_db() as db:
        players = db.execute(
            "SELECT username, is_admin, balance FROM players ORDER BY username"
        ).fetchall()
        all_players = db.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()
        admin_logs = db.execute("""
            SELECT actor, action, target, ip_address, 
                   strftime('%Y-%m-%d %H:%M', datetime(timestamp)) as timestamp
              FROM admin_log
             ORDER BY timestamp DESC
             LIMIT 50
        """).fetchall()
        auth_logs = db.execute("""
            SELECT username, success, ip_address, 
                   strftime('%Y-%m-%d %H:%M', datetime(timestamp)) as timestamp
              FROM auth_log
             ORDER BY timestamp DESC
             LIMIT 50
        """).fetchall()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "players": players,
        "all_players": all_players,
        "logs": admin_logs,
        "auth_logs": auth_logs,
        "csrf_token": request.session.get("csrf_token")
    })


def _log_action(conn, actor: str, action: str, target: str = None, ip: str = None):
    ts = datetime.now(tz=LOCAL_ZONE).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO admin_log (actor, action, target, ip_address, timestamp) VALUES (?, ?, ?, ?, ?)",
        (actor, action, target, ip, ts)
    )
    conn.commit()


@router.post("/toggle-admin", dependencies=[Depends(verify_csrf)])
def toggle_admin(
    request: Request,
    username: str = Form(...),
    user=Depends(get_current_user)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="Cannot change your own admin status")
    with get_db() as conn:
        target = conn.execute(
            "SELECT is_admin FROM players WHERE username = ?",
            (username,)
        ).fetchone()
        if target:
            new_status = 0 if target["is_admin"] else 1
            conn.execute(
                "UPDATE players SET is_admin = ? WHERE username = ?",
                (new_status, username)
            )
            _log_action(conn,
                        actor=user["username"],
                        action=f"toggle_admin={new_status}",
                        target=username,
                        ip=request.client.host)
    return RedirectResponse("/admin", status_code=302)


@router.post("/delete-user", dependencies=[Depends(verify_csrf)])
def delete_user(
    request: Request,
    username: str = Form(...),
    user=Depends(get_current_user)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    with get_db() as conn:
        conn.execute(
            "DELETE FROM players WHERE username = ?",
            (username,)
        )
        _log_action(conn,
                    actor=user["username"],
                    action="delete_user",
                    target=username,
                    ip=request.client.host)
    return RedirectResponse("/admin", status_code=302)


@router.post("/create-user", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
def create_user(
    request: Request,
    username: str = Form(...),
    is_admin: int = Form(0),
    user=Depends(get_current_user)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)
    error = None
    msg = None
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO players (username, password, is_admin, must_set_password, balance) "
                "VALUES (?, ?, ?, 1, 0)",
                (username, "", is_admin)
            )
            _log_action(conn,
                        actor=user["username"],
                        action="create_user",
                        target=username,
                        ip=request.client.host)
            msg = f"User '{username}' created."
        except sqlite3.IntegrityError:
            error = "Username already exists"

        players = conn.execute(
            "SELECT username, is_admin, balance FROM players ORDER BY username"
        ).fetchall()
        all_players = conn.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "players": players,
        "all_players": all_players,
        "error": error,
        "msg": msg,
        "csrf_token": request.session.get("csrf_token")
    })


@router.post("/reset-password", dependencies=[Depends(verify_csrf)])
def reset_password(
    request: Request,
    username: str = Form(...),
    user=Depends(get_current_user)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)
    with get_db() as conn:
        conn.execute(
            "UPDATE players SET must_set_password = 1, password = '' WHERE username = ?",
            (username,)
        )
        _log_action(conn,
                    actor=user["username"],
                    action="reset_password",
                    target=username,
                    ip=request.client.host)
    return RedirectResponse("/admin", status_code=302)


@router.post("/set-balance", dependencies=[Depends(verify_csrf)])
def set_balance(
    request: Request,
    username: str = Form(...),
    balance: int = Form(...),
    user=Depends(get_current_user)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)
    with get_db() as conn:
        conn.execute(
            "UPDATE players SET balance = ? WHERE username = ?",
            (balance, username)
        )
        _log_action(conn,
                    actor=user["username"],
                    action=f"set_balance={balance}",
                    target=username,
                    ip=request.client.host)
    return RedirectResponse("/admin", status_code=302)