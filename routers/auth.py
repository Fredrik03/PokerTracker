from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from db import get_db
from deps import get_current_user
from rate_limit import limiter

router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.get("/login")
def login_form(request: Request):
    if request.session.get("user") and not request.session.get("must_set_password"):
        return RedirectResponse("/dashboard", 302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    with get_db() as db:
        user = db.execute("SELECT * FROM players WHERE username = ?", (username,)).fetchone()

    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Username not found"})

    if user["must_set_password"]:
        request.session["user"] = username
        request.session["is_admin"] = user["is_admin"]
        request.session["must_set_password"] = True
        return RedirectResponse("/set-password", 302)

    if not pwd.verify(password, user["password"]):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid password"})

    request.session["user"] = username
    request.session["is_admin"] = user["is_admin"]
    request.session.pop("must_set_password", None)
    return RedirectResponse("/dashboard", 302)


@router.get("/set-password")
def set_pw_form(request: Request):
    user = get_current_user(request)
    if not user or not request.session.get("must_set_password"):
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse("set_password.html", {"request": request, "error": None})


@router.post("/set-password")
def set_password(request: Request,
                 new_password: str = Form(...),
                 confirm: str = Form(...)):
    user = get_current_user(request)
    if not user or not request.session.get("must_set_password"):
        return RedirectResponse("/login", 302)

    if new_password != confirm:
        return templates.TemplateResponse("set_password.html", {"request": request, "error": "Passwords do not match"})

    hashed = pwd.hash(new_password)
    with get_db() as db:
        db.execute(
            "UPDATE players SET password = ?, must_set_password = 0 WHERE username = ?",
            (hashed, user["username"])
        )
        db.commit()

    request.session.pop("must_set_password", None)
    return RedirectResponse("/dashboard", 302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 302)
