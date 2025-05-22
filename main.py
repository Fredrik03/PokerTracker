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
import db
db.init_db()

# Password hasher for bootstrap
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()
# Mount static files (absolute path)
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

# Bootstrap the admin account on startup
@app.on_event("startup")
def bootstrap_admin():
    from db import get_db
    username = config.ADMIN_USERNAME
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM players WHERE username = ?", (username,)
        ).fetchone()
        if not exists:
            # Create account requiring password set on first login
            conn.execute(
                "INSERT INTO players (username, password, is_admin, must_set_password) VALUES (?, ?, 1, 1)",
                (username, "")
            )
            conn.commit()
            print(f"[startup] Bootstrapped admin account '{username}', requires password set.")

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
        protected = ["/dashboard","/profile","/leaderboard","/player/","/monthly-stats","/global-stats","/history","/admin"]
        if any(request.url.path.startswith(p) for p in protected):
            response.headers.update({
                "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Surrogate-Control": "no-store"
            })
        return response

# Register middleware
app.add_middleware(InitialPasswordMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    https_only=True,
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
import routers.auth as auth
import routers.stats as stats
import routers.dashboard as dashboard
import routers.games as games
import routers.admin as admin
import routers.profile as profile
import routers.history as history
import routers.global_stats as global_stats
import routers.monthly_stats as monthly_stats
import routers.leaderboard as leaderboard
import routers.public_profile as public_profile

app.include_router(auth.router)
app.include_router(stats.router)
app.include_router(dashboard.router)
app.include_router(games.router)
app.include_router(admin.router)
app.include_router(profile.router)
app.include_router(history.router)
app.include_router(global_stats.router)
app.include_router(monthly_stats.router)
app.include_router(leaderboard.router)
app.include_router(public_profile.router)

# Root redirect with CSRF generation
from deps import generate_csrf
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(generate_csrf)])
async def root(request: Request):
    _ = request.session.get("csrf_token")
    return RedirectResponse("/dashboard")
