from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlite3 import DatabaseError

from deps import get_current_user
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    # 1) auth guard
    if not current_user:
        return RedirectResponse("/login", status_code=302)

    username = current_user["username"]

    try:
        with get_db() as db:
            # total sessions
            total_games = db.execute(
                "SELECT COUNT(*) FROM game_players WHERE username = ?",
                (username,),
            ).fetchone()[0] or 0

            # win rate
            win_count = db.execute(
                "SELECT COUNT(*) FROM games WHERE winner = ? AND amount > 0",
                (username,),
            ).fetchone()[0] or 0
            win_rate = round(win_count / total_games * 100, 1) if total_games else 0

            # net_sum and avg_profit
            net_sum = db.execute(
                "SELECT COALESCE(balance, 0) FROM players WHERE username = ?",
                (username,),
            ).fetchone()[0] or 0
            avg_profit = round(net_sum / total_games, 1) if total_games else 0

            # daily cumulative progress
            rows = db.execute(
                """
                SELECT g.date, SUM(gp.net) AS daily_net
                  FROM game_players gp
                  JOIN games g ON g.id = gp.game_id
                 WHERE gp.username = ?
                 GROUP BY g.date
                 ORDER BY g.date
                """,
                (username,),
            ).fetchall()

            dates = [r["date"] for r in rows]
            cumulative = []
            running = 0
            for r in rows:
                running += r["daily_net"]
                cumulative.append(running)

            # recent sessions
            recent = db.execute(
                """
                SELECT g.date, gp.net AS net
                  FROM game_players gp
                  JOIN games g ON g.id = gp.game_id
                 WHERE gp.username = ?
                 ORDER BY g.date DESC
                 LIMIT 10
                """,
                (username,),
            ).fetchall()

    except DatabaseError:
        # 2) don’t leak internals
        raise HTTPException(status_code=500, detail="Unable to load dashboard data")

    # 3) render safely
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request":     request,
            "username":    username,
            "total_games": total_games,
            "win_rate":    win_rate,
            "net_sum":     net_sum,
            "avg_profit":  avg_profit,
            "dates":       dates,
            "cumulative":  cumulative,
            "recent":      recent,
        },
    )
