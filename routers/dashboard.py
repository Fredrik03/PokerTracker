from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from deps import get_current_user
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)

    username = user["username"]
    with get_db() as db:
        # same queries here
        total_games = db.execute(
            "SELECT COUNT(*) FROM games WHERE winner = ?",
            (username,)
        ).fetchone()[0]

        win_count = db.execute(
            "SELECT COUNT(*) FROM games WHERE winner = ? AND amount > 0",
            (username,)
        ).fetchone()[0]

        win_rate = round((win_count / total_games * 100), 1) if total_games else 0

        net_sum = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM games WHERE winner = ?",
            (username,)
        ).fetchone()[0]

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
        "dashboard.html",
        {
            "request":      request,
            "username":     username,
            "total_games":  total_games,
            "win_rate":     win_rate,
            "net_sum":      net_sum,
            "avg_profit":   avg_profit,
            "dates":        dates,
            "cumulative":   cumulative,
            "recent":       recent,
        }
    )
