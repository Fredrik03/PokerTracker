from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from db import get_db
from deps import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.get("/profile", response_class=HTMLResponse)
def profile(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    with get_db() as db:
        history = db.execute(
            "SELECT date, amount FROM games WHERE winner = ? ORDER BY date DESC",
            (user["username"],)
        ).fetchall()
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "username": user["username"],
            "balance": user["balance"],
            "is_admin": user["is_admin"],
            "history": history,
            "error": None,
            "msg": None
        }
    )


@router.post("/profile/change-password", response_class=HTMLResponse)
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
                "UPDATE players SET password = ? WHERE username = ?",
                (hashed, user["username"])
            )
            db.commit()
        msg = "Password updated successfully."

    with get_db() as db:
        history = db.execute(
            "SELECT date, amount FROM games WHERE winner = ? ORDER BY date DESC",
            (user["username"],)
        ).fetchall()

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "username": user["username"],
            "balance": user["balance"],
            "is_admin": user["is_admin"],
            "history": history,
            "error": error,
            "msg": msg
        }
    )
