# main.py

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from passlib.context import CryptContext

# ✅ Import your shared limiter from rate_limit.py
from rate_limit import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

import config, db
from deps import get_current_user
from routers import auth, stats, dashboard, games, admin, profile, history, global_stats, monthly_stats

# 1) initialize DB
db.init_db()
app = FastAPI()

# ✅ 1a) attach limiter to app
app.state.limiter = limiter

# ✅ 1b) global exception handler for rate-limiting
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Too many requests. Please try again later."}
    )

# password hasher for bootstrap
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 2) bootstrap admin on startup
@app.on_event("startup")
def bootstrap_admin():
    from db import get_db
    username = config.ADMIN_USERNAME

    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM players WHERE username = ?", (username,)
        ).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO players
                  (username, password, is_admin, must_set_password)
                VALUES (?, ?, 1, 1)
                """,
                (username, "")
            )
            conn.commit()
            print(f"[startup] bootstrapped admin account '{username}', will require setting password on first login")

# 3) "must-set-password" guard
class InitialPasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            request.session.get("user") and
            request.session.get("must_set_password") and
            not request.url.path.startswith(("/login", "/set-password", "/static", "/logout"))
        ):
            return RedirectResponse("/set-password", status_code=302)
        return await call_next(request)

# 4) NoCacheMiddleware to prevent caching on protected routes
class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        protected_paths = [
            "/dashboard",
            "/profile",
            "/leaderboard",
            "/player/",        # trailing slash to catch subpaths like /player/username
            "/monthly-stats",
            "/global-stats",
            "/history",
            "/admin",
        ]
        if any(request.url.path.startswith(path) for path in protected_paths):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["Surrogate-Control"] = "no-store"
        return response


# ✅ Middleware registration
app.add_middleware(InitialPasswordMiddleware)
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET)
app.add_middleware(SlowAPIMiddleware)  # Enables limiter to track requests
app.add_middleware(NoCacheMiddleware)  # Add the no-cache middleware last

# 5) templating & static
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 6) routers
app.include_router(auth.router)
app.include_router(stats.router)
app.include_router(dashboard.router)
app.include_router(games.router)
app.include_router(admin.router)
app.include_router(profile.router)
app.include_router(history.router)
app.include_router(global_stats.router)
app.include_router(monthly_stats.router)

# 7) dashboard (and root)
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/dashboard")
