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
            # Aggregate stats for the user
            stats = db.execute("""
                               WITH user_stats AS (SELECT COUNT(*)                                   as total_games,
                                                          COALESCE(SUM(buyin), 0)                    as total_buyin,
                                                          COALESCE(SUM(rebuys), 0)                   as total_rebuys,
                                                          COALESCE(SUM(buyin + (rebuys * buyin)), 0) as total_invested,
                                                          MAX(net)                                   as biggest_win,
                                                          MIN(net)                                   as biggest_loss
                                                   FROM game_players
                                                   WHERE username = ?)
                               SELECT s.*,
                                      p.balance as net_sum,
                                      CASE
                                          WHEN s.total_invested > 0
                                              THEN ROUND(CAST(p.balance AS FLOAT) / s.total_invested * 100, 2)
                                          ELSE 0
                                          END   as roi
                               FROM user_stats s
                                        JOIN players p ON p.username = ?
                               """, (username, username)).fetchone()

            # Win rate calculation
            win_count = db.execute(
                "SELECT COUNT(*) FROM games WHERE winner = ? AND amount > 0",
                (username,),
            ).fetchone()[0] or 0

            total_games = stats["total_games"]
            win_rate = round(win_count / total_games * 100, 1) if total_games else 0
            avg_profit = round(stats["net_sum"] / total_games, 1) if total_games else 0

            # Cumulative progress chart data
            rows = db.execute("""
                              SELECT g.date, SUM(gp.net) AS daily_net
                              FROM game_players gp
                                       JOIN games g ON g.id = gp.game_id
                              WHERE gp.username = ?
                              GROUP BY g.date
                              ORDER BY g.date
                              """, (username,)).fetchall()

            dates = [r["date"] for r in rows]
            cumulative = []
            running = 0
            for r in rows:
                running += r["daily_net"]
                cumulative.append(running)

            # Recent sessions
            recent = db.execute("""
                                SELECT g.date, gp.net AS net
                                FROM game_players gp
                                         JOIN games g ON g.id = gp.game_id
                                WHERE gp.username = ?
                                ORDER BY g.date DESC LIMIT 10
                                """, (username,)).fetchall()

    except DatabaseError:
        raise HTTPException(status_code=500, detail="Unable to load dashboard data")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "username": username,
            "total_games": total_games,
            "win_rate": win_rate,
            "net_sum": stats["net_sum"],
            "avg_profit": avg_profit,
            "dates": dates,
            "cumulative": cumulative,
            "recent": recent,
            "roi": stats["roi"],
            "total_buyin": stats["total_invested"],
            "biggest_win": stats["biggest_win"],
            "biggest_loss": stats["biggest_loss"],
            "total_rebuys": stats["total_rebuys"]
        },
    )
