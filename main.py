# main.py

from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

import config, db
from deps import get_current_user
from routers import auth, stats, dashboard, games, admin, profile, history, global_stats, monthly_stats

# 1) initialize DB
db.init_db()

app = FastAPI()


# 3) then your “must-set-password” guard as BaseHTTPMiddleware
class InitialPasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # if they’re flagged and not on an auth/static path, redirect them
        if (
            request.session.get("user")
            and request.session.get("must_set_password")
            and not request.url.path.startswith((
                "/login","/register","/set-password","/static","/logout"
            ))
        ):
            return RedirectResponse("/set-password", status_code=302)
        return await call_next(request)

app.add_middleware(InitialPasswordMiddleware)

app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET)

# 4) templating & static
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 5) routers
app.include_router(auth.router)
app.include_router(stats.router)
app.include_router(dashboard.router)
app.include_router(games.router)
app.include_router(admin.router)
app.include_router(profile.router)
app.include_router(history.router)
app.include_router(global_stats.router)
app.include_router(monthly_stats.router)

# 6) dashboard (and root)
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

