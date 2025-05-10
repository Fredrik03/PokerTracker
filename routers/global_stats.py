from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from deps import get_current_user
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/global-stats")
def global_stats(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    with get_db() as db:
        total_games = db.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        total_money = db.execute("SELECT COALESCE(SUM(amount), 0) FROM games").fetchone()[0]
        unique_winners = db.execute("SELECT COUNT(DISTINCT winner) FROM games").fetchone()[0]

        # ✅ Fetch top 5 players instead of 1
        top_players = db.execute("""
            SELECT winner, SUM(amount) AS total_won
            FROM games
            GROUP BY winner
            ORDER BY total_won DESC
            LIMIT 5
        """).fetchall()

    top_player = top_players[0][0] if top_players else "No games yet"

    return templates.TemplateResponse("global_stats.html", {
        "request": request,
        "total_games": total_games,
        "total_money": total_money,
        "unique_winners": unique_winners,
        "top_players": top_players,  # ✅ send the list to template
        "top_player": top_player,
    })


@router.get("/global-stats-data", response_class=JSONResponse)
def global_stats_data():
    with get_db() as db:
        players = [r["username"] for r in db.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()]

        dates = [r["date"] for r in db.execute(
            "SELECT DISTINCT date FROM games ORDER BY date"
        ).fetchall()]

        cumul = {p: 0 for p in players}
        series = {p: [] for p in players}

        for d in dates:
            today = {r["winner"]: r["amount"] for r in db.execute(
                "SELECT winner, amount FROM games WHERE date = ?", (d,)
            ).fetchall()}
            for p in players:
                cumul[p] += today.get(p, 0)
                series[p].append(cumul[p])

    datasets = [{"label": p, "data": series[p], "fill": False, "borderWidth": 2}
                for p in players]

    return JSONResponse({"labels": dates, "datasets": datasets})
