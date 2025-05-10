# routers/stats.py

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_db
from deps import get_current_user   # or wherever you define it

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=None)
def index(request: Request):
    # public landing page
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/leaderboard", response_class=HTMLResponse)
def leaderboard(request: Request, sort: str = "balance"):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login",302)

    # map the incoming ?sort= key to an actual SQL alias
    sort_map = {
        "balance":    "p.balance",
        "games":      "games_played",
        "rebuys":     "total_rebuys",
    }
    sort_col = sort_map.get(sort, "p.balance")

    with get_db() as db:
        rows = db.execute(f"""
            SELECT
              p.username,
              p.balance,
              COUNT(g.rowid)       AS games_played,
              COALESCE(SUM(g.rebuys),0) AS total_rebuys
            FROM players p
            LEFT JOIN games g
              ON g.winner = p.username
            GROUP BY p.username
            ORDER BY {sort_col} DESC
        """).fetchall()

    return templates.TemplateResponse(
        "leaderboard.html",
        {
            "request": request,
            "players": rows,
            "current_sort": sort
        }
    )


@router.get("/progress", response_class=None)
def progress(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse("progress.html", {"request": request})


@router.get("/progress-data", response_class=JSONResponse)
def progress_data():
    with get_db() as db:
        # get all players
        players = [r["username"] for r in db.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()]

        # distinct, sorted game dates
        dates = [r["date"] for r in db.execute(
            "SELECT DISTINCT date FROM games ORDER BY date"
        ).fetchall()]

        # build running totals
        cumul = {p: 0 for p in players}
        series = {p: [] for p in players}

        for d in dates:
            today = {
                r["winner"]: r["amount"]
                for r in db.execute(
                    "SELECT winner, amount FROM games WHERE date = ?",
                    (d,)
                ).fetchall()
            }
            for p in players:
                cumul[p] += today.get(p, 0)
                series[p].append(cumul[p])

    datasets = [
        {"label": p, "data": series[p], "fill": False, "borderWidth": 2}
        for p in players
    ]

    return JSONResponse({"labels": dates, "datasets": datasets})



