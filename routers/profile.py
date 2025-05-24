from fastapi import APIRouter, Request, Form, Depends, HTTPException, File, UploadFile
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlite3 import DatabaseError
import os
import shutil
from uuid import uuid4
from pathlib import Path

from deps import get_current_user, tenant_required, get_tenant_db, generate_csrf, verify_csrf
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.get(
    "/profile",
    response_class=HTMLResponse,
    dependencies=[Depends(generate_csrf), Depends(tenant_required)]
)
def profile(
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_tenant_db)
):
    if not user:
        return RedirectResponse("/login", status_code=302)

    tenant_id = request.state.tenant_id

    try:
        # Fetch full user record for this tenant
        full_user = db.execute(
            "SELECT * FROM players WHERE username = ? AND tenant_id = ?",
            (user["username"], tenant_id)
        ).fetchone()

        history = db.execute(
            "SELECT date, amount FROM games WHERE winner = ? AND tenant_id = ? ORDER BY date DESC",
            (user["username"], tenant_id)
        ).fetchall()

    except DatabaseError:
        raise HTTPException(500, "Unable to load profile data")

    avatar = full_user["avatar_path"] if full_user else None


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


@router.post(
    "/profile/change-password",
    response_class=HTMLResponse,
    dependencies=[Depends(verify_csrf), Depends(tenant_required)]
)
def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    user=Depends(get_current_user),
    db=Depends(get_tenant_db)
):
    if not user:
        return RedirectResponse("/login", status_code=302)

    tenant_id = request.state.tenant_id

    # Fetch full user data again to use in response context
    full_user = db.execute(
        "SELECT * FROM players WHERE username = ? AND tenant_id = ?",
        (user["username"], tenant_id)
    ).fetchone()

    history = db.execute(
        "SELECT date, amount FROM games WHERE winner = ? AND tenant_id = ? ORDER BY date DESC",
        (user["username"], tenant_id)
    ).fetchall()

    stored = db.execute(
        "SELECT password FROM players WHERE username = ? AND tenant_id = ?",
        (user["username"], tenant_id)
    ).fetchone()

    if not stored or not pwd.verify(old_password, stored["password"]):
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "username": user["username"],
                "balance": user.get("balance"),
                "is_admin": bool(user.get("is_admin")),
                "avatar_path": full_user.get("avatar_path") if full_user else None,
                "history": history,
                "error": "Old password is incorrect.",
                "msg": None,
                "csrf_token": request.session.get("csrf_token"),
            }
        )

    # Update to new password
    hashed = pwd.hash(new_password)
    db.execute(
        "UPDATE players SET password = ?, password_changed_at = ? WHERE username = ? AND tenant_id = ?",
        (hashed, datetime.utcnow().isoformat(), user["username"], tenant_id)
    )
    db.commit()

    return RedirectResponse("/profile", status_code=302)


@router.post(
    "/profile/avatar",
    response_class=HTMLResponse,
    dependencies=[Depends(verify_csrf), Depends(tenant_required)]
)
async def update_avatar(
        request: Request,
        file: UploadFile = File(...),
        user=Depends(get_current_user),
        db=Depends(get_tenant_db)
):
    if not user:
        return RedirectResponse("/login", status_code=302)

    tenant_id = request.state.tenant_id

    # Generate unique filename
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "username": user["username"],
                "balance": user["balance"],
                "is_admin": user["is_admin"],
                "avatar_path": None,
                "error": "Invalid file type. Please upload an image file.",
                "csrf_token": request.session.get("csrf_token"),
            }
        )

    unique_filename = f"{uuid4()}{file_extension}"
    avatar_path = f"avatars/{unique_filename}"
    file_path = BASE_DIR / "static" / avatar_path

    # Save the file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Update database with new path
        db.execute(
            "UPDATE players SET avatar_path = ? WHERE username = ? AND tenant_id = ?",
            (avatar_path, user["username"], tenant_id)
        )
        db.commit()

        return RedirectResponse("/profile", status_code=302)
    except Exception as e:
        raise HTTPException(500, f"Unable to update avatar: {str(e)}")
    finally:
        file.file.close()

    return RedirectResponse("/profile", status_code=302)
