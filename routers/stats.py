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
              p.avatar_path,  -- ✅ Add this
              COUNT(g.rowid) AS games_played,
              COALESCE(SUM(g.rebuys), 0) AS total_rebuys
            FROM players p
            LEFT JOIN games g ON g.winner = p.username
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
@router.get("/player/{username}", response_class=HTMLResponse)
def public_dashboard(username: str, request: Request):
    with get_db() as db:
        user_row = db.execute(
            "SELECT username, balance, avatar_path FROM players WHERE username = ?",
            (username,)
        ).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        # Use game_players for total sessions (all participations)
        total_games = db.execute(
            "SELECT COUNT(*) FROM game_players WHERE username = ?",
            (username,)
        ).fetchone()[0] or 0

        # Wins (amount > 0) from games table
        win_count = db.execute(
            "SELECT COUNT(*) FROM games WHERE winner = ? AND amount > 0",
            (username,)
        ).fetchone()[0] or 0

        win_rate = round((win_count / total_games * 100), 1) if total_games else 0

        net_sum = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM games WHERE winner = ?",
            (username,)
        ).fetchone()[0] or 0

        avg_profit = round((net_sum / total_games), 1) if total_games else 0

        rows = db.execute(
            """
            SELECT date, SUM(amount) AS daily_net
            FROM games
            WHERE winner = ?
            GROUP BY date
            ORDER BY date
            """,
            (username,)
        ).fetchall()

        dates = [r["date"] for r in rows]
        cumulative = []
        running = 0
        for r in rows:
            running += r["daily_net"]
            cumulative.append(running)

        recent = db.execute(
            """
            SELECT date, amount AS net
            FROM games
            WHERE winner = ?
            ORDER BY date DESC
            LIMIT 10
            """,
            (username,)
        ).fetchall()

    return templates.TemplateResponse(
        "public_dashboard.html",
        {
            "request": request,
            "username": user_row["username"],
            "avatar_path": user_row["avatar_path"],
            "balance": user_row["balance"],
            "total_games": total_games,         # Pass this
            "win_rate": win_rate,
            "net_sum": net_sum,
            "avg_profit": avg_profit,
            "dates": dates,
            "cumulative": cumulative,
            "recent": recent,
        }
    )



