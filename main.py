import config
import db
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from passlib.context import CryptContext

# Initialize database
db.init_db()

# Password hasher for bootstrap
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()

# Mount static files
BASE_DIR = Path(__file__).resolve().parent
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static"
)

# Rate limiter
from rate_limit import limiter
app.state.limiter = limiter
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": "Too many requests."})

# Middleware
class InitialPasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            request.session.get("user") and
            request.session.get("must_set_password") and
            not request.url.path.startswith(("/login", "/set-password", "/static", "/logout"))
        ):
            return RedirectResponse("/set-password", 302)
        return await call_next(request)

class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        protected = [
            "/dashboard","/profile","/leaderboard","/player/",
            "/monthly-stats","/history","/admin"
        ]
        if any(request.url.path.startswith(p) for p in protected):
            response.headers.update({
                "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Surrogate-Control": "no-store"
            })
        return response

# Register middleware
from middlewares.tenant_middleware import tenant_middleware
app.middleware("http")(tenant_middleware) 
app.add_middleware(InitialPasswordMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    https_only=False,
    same_site="strict",
    session_cookie="session",
    max_age=14 * 24 * 3600
)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(NoCacheMiddleware)
from security import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Include routers
import routers.auth           as auth
import routers.stats          as stats
import routers.dashboard      as dashboard
import routers.games          as games
import routers.admin          as site_admin      # site-only tenant admin
import routers.super_admin    as super_admin     # global super-admin
import routers.profile        as profile
import routers.history        as history
import routers.leaderboard    as leaderboard
import routers.public_profile as public_profile

app.include_router(auth.router)
app.include_router(stats.router)
app.include_router(dashboard.router)
app.include_router(games.router)

# 1) Tenant-scoped "site admin" comes first
app.include_router(site_admin.router)

# 2) Global "super-admin" on bare domain only
app.include_router(super_admin.router)

# 3) All other tenant-scoped routers
app.include_router(profile.router)
app.include_router(history.router)
# monthly_stats removed since not used
app.include_router(leaderboard.router)
app.include_router(public_profile.router)

# Root redirect with CSRF generation
from deps import generate_csrf

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(generate_csrf)])
async def root(request: Request):
    host = request.headers.get("host", "").split(":")[0]
    base = config.BASE_DOMAIN

    # If root domain: redirect to super admin login
    if host == base or "localhost" in host or "127." in host:
        return RedirectResponse("/admin/login", status_code=302)

    # Otherwise: normal tenant user flow
    _ = request.session.get("csrf_token")
    if request.session.get("user") and not request.session.get("must_set_password"):
        return RedirectResponse("/dashboard", 302)
    return templates.TemplateResponse("index.html", {"request": request})
