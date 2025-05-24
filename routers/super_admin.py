from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from slowapi.errors import RateLimitExceeded
from rate_limit import limiter  # ✅ use the global limiter you've defined
from db import get_db
from typing import Optional
import uuid
from db import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Templates and rate limiter
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin", tags=["super-admin"])


async def superadmin_required(request: Request):
    if not request.session.get("super_admin_user_id"):
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Redirect to login",
            headers={"Location": "/admin/login"},
        )


class TenantCreateForm(BaseModel):
    name: str = Field(
        ..., min_length=3, max_length=30,
        pattern=r"^[a-z0-9\-]+$"
    )
    site_admin_username: str = Field(
        ..., min_length=3, max_length=30,
        pattern=r"^[A-Za-z0-9_]+$"
    )
    site_admin_password: str = Field(..., min_length=8)
    owner_id: Optional[str] = None


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = uuid.uuid4().hex
    return templates.TemplateResponse(
        "super_admin_login.html",
        {"request": request, "csrf_token": request.session["csrf_token"]}
    )


@router.post("/login")
@limiter.limit("5/minute")  # 💡 5 login attempts per IP per minute
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(400, "Invalid CSRF token")

    conn = get_db()
    row = conn.execute(
        "SELECT id, password, is_superadmin FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not pwd_context.verify(password, row["password"]):
        return templates.TemplateResponse(
            "super_admin_login.html",
            {"request": request, "error": "Invalid credentials",
             "csrf_token": request.session.get("csrf_token")},
            status_code=400,
        )
    if row["is_superadmin"] != 1:
        raise HTTPException(403, "Not a super-admin")

    request.session["super_admin_user_id"] = row["id"]
    request.session["csrf_token"] = uuid.uuid4().hex
    return RedirectResponse("/admin/tenants", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


@router.get("/tenants", dependencies=[Depends(superadmin_required)])
async def list_tenants(request: Request):
    conn = get_db()
    tenants = conn.execute(
        "SELECT id, name, owner_id, created_at FROM tenants ORDER BY created_at DESC"
    ).fetchall()
    return templates.TemplateResponse(
        "super_admin_tenants.html",
        {
            "request": request,
            "tenants": tenants,
            "csrf_token": request.session.get("csrf_token"),
        },
    )


@router.post("/tenants", dependencies=[Depends(superadmin_required)])
async def create_tenant(
    request: Request,
    name: str = Form(...),
    site_admin_username: str = Form(...),
    site_admin_password: str = Form(...),
    owner_id: Optional[str] = Form(None),
    csrf_token: str = Form(...),
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(400, "Invalid CSRF token")

    if not re.fullmatch(r"^[a-z0-9\-]{3,30}$", name):
        raise HTTPException(400, "Invalid site name")
    if not re.fullmatch(r"^[A-Za-z0-9_]{3,30}$", site_admin_username):
        raise HTTPException(400, "Invalid admin username")
    if len(site_admin_password) < 8:
        raise HTTPException(400, "Password too short")

    conn = get_db()

    if conn.execute("SELECT 1 FROM tenants WHERE name = ?", (name,)).fetchone():
        tenants = conn.execute(
            "SELECT id, name, owner_id, created_at FROM tenants"
        ).fetchall()
        return templates.TemplateResponse(
            "super_admin_tenants.html",
            {"request": request, "error": "Site already exists",
             "tenants": tenants, "csrf_token": request.session.get("csrf_token")},
            status_code=400,
        )

    if conn.execute("SELECT 1 FROM players WHERE username = ? AND tenant_id = ?", (site_admin_username, name)).fetchone():
        tenants = conn.execute(
            "SELECT id, name, owner_id, created_at FROM tenants"
        ).fetchall()
        return templates.TemplateResponse(
            "super_admin_tenants.html",
            {"request": request, "error": "Admin username taken",
             "tenants": tenants, "csrf_token": request.session.get("csrf_token")},
            status_code=400,
        )

    tenant_id = uuid.uuid4().hex
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO tenants (id, name, owner_id, created_at) VALUES (?, ?, ?, ?)",
        (tenant_id, name, None, now),
    )
    hashed_pw = pwd_context.hash(site_admin_password)
    conn.execute(
        "INSERT INTO players (username, password, is_admin, must_set_password, tenant_id) VALUES (?, ?, 1, 1, ?)",
        (site_admin_username, hashed_pw, tenant_id),
    )
    conn.commit()

    request.session["csrf_token"] = uuid.uuid4().hex
    return RedirectResponse("/admin/tenants", status_code=302)


@router.post("/tenants/delete", dependencies=[Depends(superadmin_required)])
async def delete_tenant(
    request: Request,
    name: str = Form(...),
    csrf_token: str = Form(...),
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(400, "Invalid CSRF token")
    if not re.fullmatch(r"^[a-z0-9\-]{3,30}$", name):
        raise HTTPException(400, "Invalid site name")

    conn = get_db()
    conn.execute("DELETE FROM tenants WHERE name = ?", (name,))
    conn.execute("DELETE FROM players WHERE tenant_id = ?", (name,))
    conn.commit()

    request.session["csrf_token"] = uuid.uuid4().hex
    return RedirectResponse("/admin/tenants", status_code=302)
