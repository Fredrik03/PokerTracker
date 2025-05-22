from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from db import get_db
from deps import get_current_user, generate_csrf, verify_csrf
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.get("/profile", response_class=HTMLResponse, dependencies=[Depends(generate_csrf)])
def profile(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    with get_db() as db:
        full_user = db.execute("SELECT * FROM players WHERE username = ?", (user["username"],)).fetchone()
        history = db.execute(
            "SELECT date, amount FROM games WHERE winner = ? ORDER BY date DESC", (user["username"],)
        ).fetchall()

    # Safely access avatar_path column
    avatar = full_user["avatar_path"] if "avatar_path" in full_user.keys() else None

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "username": user["username"],
            "balance": user["balance"],
            "is_admin": user["is_admin"],
            "avatar_path": avatar,
            "history": history,
            "error": None,
            "msg": None,
            "csrf_token": request.session.get("csrf_token"),
        }
    )

@router.post("/profile/change-password", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    user=Depends(get_current_user)
):
    if not user:
        return RedirectResponse("/login", status_code=302)
    error = None
    msg = None
    if not pwd.verify(old_password, user["password"]):
        error = "Old password is incorrect."
    else:
        hashed = pwd.hash(new_password)
        with get_db() as db:
            db.execute(
                "UPDATE players SET password = ? WHERE username = ?", (hashed, user["username"])
            )
            db.commit()
        msg = "Password updated successfully."
    with get_db() as db:
        full_user = db.execute("SELECT * FROM players WHERE username = ?", (user["username"],)).fetchone()
        history = db.execute(
            "SELECT date, amount FROM games WHERE winner = ? ORDER BY date DESC", (user["username"],)
        ).fetchall()
    avatar = full_user["avatar_path"] if "avatar_path" in full_user.keys() else None
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "username": user["username"],
            "balance": user["balance"],
            "is_admin": user["is_admin"],
            "avatar_path": avatar,
            "history": history,
            "error": error,
            "msg": msg,
            "csrf_token": request.session.get("csrf_token"),
        }
    )

@router.post("/profile/avatar", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
def update_avatar(
    request: Request,
    avatar_path: str = Form(...),
    user=Depends(get_current_user)
):
    if not user:
        return RedirectResponse("/login", status_code=302)
    with get_db() as db:
        db.execute(
            "UPDATE players SET avatar_path = ? WHERE username = ?", (avatar_path, user["username"])
        )
        db.commit()
        full_user = db.execute("SELECT * FROM players WHERE username = ?", (user["username"],)).fetchone()
        history = db.execute(
            "SELECT date, amount FROM games WHERE winner = ? ORDER BY date DESC", (user["username"],)
        ).fetchall()
    avatar = full_user["avatar_path"] if "avatar_path" in full_user.keys() else None
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "username": user["username"],
            "balance": user["balance"],
            "is_admin": user["is_admin"],
            "avatar_path": avatar,
            "history": history,
            "error": None,
            "msg": "Avatar updated successfully!",
            "csrf_token": request.session.get("csrf_token"),
        }
    )
