from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from deps import get_current_user
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")   # ← make sure this is here


@router.get("/admin")
def admin_panel(request: Request):
    user = get_current_user(request)
    if not user or user["is_admin"] != 1:
        return RedirectResponse("/dashboard", status_code=302)

    with get_db() as db:
        # for user-management table
        players     = db.execute(
            "SELECT username, is_admin FROM players ORDER BY username"
        ).fetchall()
        # for the Add Game participant list
        all_players = db.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()

    return templates.TemplateResponse("admin.html", {
        "request":     request,
        "players":     players,
        "all_players": all_players,   # ← make sure you include this
    })

@router.post("/toggle-admin")
def toggle_admin(request: Request, username: str = Form(...), user=Depends(get_current_user)):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)
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
            conn.commit()
    return RedirectResponse("/admin", status_code=302)

@router.post("/delete-user")
def delete_user(request: Request, username: str = Form(...), user=Depends(get_current_user)):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403)
    if username != user["username"]:
        with get_db() as conn:
            conn.execute("DELETE FROM players WHERE username = ?", (username,))
            conn.commit()
    return RedirectResponse("/admin", status_code=302)
@router.post("/create-user", response_class=HTMLResponse)
def create_user(
    request: Request,
    username: str = Form(...),
    is_admin: int = Form(0),
    user=Depends(get_current_user)
):
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403, detail="Not allowed")

    error = None
    msg   = None
    with get_db() as db:
        try:
            db.execute(
                """
                INSERT INTO players (username, password, is_admin, must_set_password)
                VALUES (?, ?, ?, 1)
                """,
                (username, "", is_admin)
            )
            db.commit()
            msg = f"User '{username}' created."
        except sqlite3.IntegrityError:
            error = "Username already exists"

        # **always** re-fetch both lists
        players     = db.execute(
            "SELECT username, is_admin FROM players ORDER BY username"
        ).fetchall()
        all_players = db.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request":      request,
            "players":      players,
            "all_players":  all_players,
            "error":        error,
            "msg":          msg,
        }
    )

