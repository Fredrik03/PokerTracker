from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from db import get_db
from deps import get_current_user, generate_csrf, verify_csrf
from rate_limit import limiter
import re
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Constants for security
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bcrypt maximum
MAX_USERNAME_LENGTH = 32
PASSWORD_PATTERN = re.compile(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d@$!%*#?&]{8,}$')

def validate_username(username: str) -> str:
    """Validerer brukernavn format og lengde"""
    if not username or not isinstance(username, str):
        raise HTTPException(status_code=400, detail="Username is required")
    username = username.strip()
    if not 3 <= len(username) <= MAX_USERNAME_LENGTH:
        raise HTTPException(status_code=400, detail="Username must be between 3 and 32 characters")
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        raise HTTPException(status_code=400, detail="Username contains invalid characters")
    return username

def validate_password(password: str) -> str:
    """Validerer passord styrke og lengde"""
    if not password or not isinstance(password, str):
        raise HTTPException(status_code=400, detail="Password is required")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters"
        )
    if not PASSWORD_PATTERN.match(password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one letter, one number, and be at least 8 characters long"
        )
    return password

def log_auth_attempt(db, username: str, success: bool, ip: str):
    """Logger autentiseringsforsøk for sikkerhet"""
    db.execute(
        """INSERT INTO auth_log (username, success, ip_address, timestamp)
           VALUES (?, ?, ?, ?)""",
        (username, success, ip, datetime.utcnow().isoformat())
    )
    db.commit()

@router.get("/login", dependencies=[Depends(generate_csrf)])
async def login_form(request: Request):
    if request.session.get("user") and not request.session.get("must_set_password"):
        return RedirectResponse("/dashboard", 302)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None, "csrf_token": request.session.get("csrf_token")}
    )

@router.post("/login", dependencies=[Depends(verify_csrf)])
@limiter.limit("5/minute")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    try:
        username = validate_username(username)
        password = validate_password(password)
    except HTTPException as e:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": e.detail, "csrf_token": request.session.get("csrf_token")}
        )
    with get_db() as db:
        user = db.execute(
            "SELECT * FROM players WHERE username = ?",
            (username,)
        ).fetchone()
        success = False
        if user:
            if user["must_set_password"]:
                request.session["user"] = username
                request.session["is_admin"] = user["is_admin"]
                request.session["must_set_password"] = True
                success = True
                log_auth_attempt(db, username, success, request.client.host)
                return RedirectResponse("/set-password", 302)
            if pwd.verify(password, user["password"]):
                success = True
                request.session["user"] = username
                request.session["is_admin"] = user["is_admin"]
                request.session.pop("must_set_password", None)
                request.session["_session_id"] = pwd.hash(username + str(datetime.utcnow()))
                log_auth_attempt(db, username, success, request.client.host)
                return RedirectResponse("/dashboard", 302)
        log_auth_attempt(db, username, success, request.client.host)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password", "csrf_token": request.session.get("csrf_token")}
        )

@router.get("/set-password", dependencies=[Depends(generate_csrf)])
async def set_pw_form(request: Request):
    user = get_current_user(request)
    if not user or not request.session.get("must_set_password"):
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse(
        "set_password.html",
        {"request": request, "error": None, "csrf_token": request.session.get("csrf_token")}
    )

@router.post("/set-password", dependencies=[Depends(verify_csrf)])
async def set_password(
    request: Request,
    new_password: str = Form(...),
    confirm: str = Form(...)
):
    user = get_current_user(request)
    if not user or not request.session.get("must_set_password"):
        return RedirectResponse("/login", 302)
    try:
        new_password = validate_password(new_password)
    except HTTPException as e:
        return templates.TemplateResponse(
            "set_password.html",
            {"request": request, "error": e.detail, "csrf_token": request.session.get("csrf_token")}
        )
    if new_password != confirm:
        return templates.TemplateResponse(
            "set_password.html",
            {"request": request, "error": "Passwords do not match", "csrf_token": request.session.get("csrf_token")}
        )
    hashed = pwd.hash(new_password)
    with get_db() as db:
        db.execute(
            """UPDATE players
               SET password = ?, 
                   must_set_password = 0,
                   password_changed_at = ?
               WHERE username = ?""",
            (hashed, datetime.utcnow().isoformat(), user["username"])
        )
        db.commit()
    request.session.pop("must_set_password", None)
    request.session["_session_id"] = pwd.hash(user["username"] + str(datetime.utcnow()))
    return RedirectResponse("/dashboard", 302)

@router.get("/register", dependencies=[Depends(generate_csrf)])
async def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "error": None, "csrf_token": request.session.get("csrf_token")}
    )

@router.post("/register", dependencies=[Depends(verify_csrf)])
@limiter.limit("5/minute")
async def register_username(
    request: Request,
    username: str = Form(...)
):
    try:
        username = validate_username(username)
    except HTTPException as e:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": e.detail, "csrf_token": request.session.get("csrf_token")}
        )
    with get_db() as db:
        user = db.execute(
            "SELECT * FROM players WHERE username = ?",
            (username,)
        ).fetchone()
        if not user:
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": "This account has not yet been created. Please contact the admin.", "csrf_token": request.session.get("csrf_token")}
            )
        if not user["must_set_password"]:
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": "This account has already been registered. Please log in instead.", "csrf_token": request.session.get("csrf_token")}
            )
        request.session["user"] = username
        request.session["is_admin"] = user["is_admin"]
        request.session["must_set_password"] = True
        log_auth_attempt(db, username, True, request.client.host)
    return RedirectResponse("/set-password", status_code=302)

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 302)
