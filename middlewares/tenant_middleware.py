# middlewares/tenant_middleware.py
from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from db import get_db
import config
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

async def tenant_middleware(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0]
    base = config.BASE_DOMAIN

    # Allow access to bare domain or dev environments
    if host == base or "localhost" in host or "127." in host:
        request.state.tenant_id = None
        return await call_next(request)

    if not host.endswith(f".{base}"):
        return templates.TemplateResponse(
            "error/404.html",
            {"request": request, "subdomain": host},
            status_code=404
        )

    subdomain = host[:-len(f".{base}")]

    with get_db() as conn:
        row = conn.execute("SELECT id FROM tenants WHERE name = ?", (subdomain,)).fetchone()

    if not row:
        return templates.TemplateResponse(
            "error/404.html",
            {"request": request, "subdomain": subdomain},
            status_code=404
        )

    request.state.tenant_id = row["id"]
    return await call_next(request)
