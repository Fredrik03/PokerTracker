# middleware/subdomain_checker.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

from db import get_main_db  # Connects to the global "tenants" DB

templates = Jinja2Templates(directory="templates")

class SubdomainValidatorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "")
        subdomain = host.split(".")[0] if "." in host else None

        # Allow direct IP access or development host bypass
        if host.startswith("localhost") or host.startswith("127.") or not subdomain:
            return await call_next(request)

        with get_main_db() as db:
            result = db.execute("SELECT 1 FROM tenants WHERE name = ?", (subdomain,)).fetchone()

        if not result:
            return templates.TemplateResponse(
                "error/404.html",
                {"request": request, "subdomain": subdomain},
                status_code=404
            )

        # Attach subdomain info to request state if needed
        request.state.subdomain = subdomain

        return await call_next(request)
