from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlite3 import DatabaseError
import traceback

from deps import get_current_user, tenant_required, get_tenant_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    dependencies=[Depends(tenant_required)]
)
def dashboard(
    request: Request,
    current_user=Depends(get_current_user),
    db=Depends(get_tenant_db)
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    username = current_user["username"]
    tenant_id = request.state.tenant_id

    try:
        # Aggregate stats
        stats = db.execute(
            """
            WITH user_stats AS (
              SELECT COUNT(*)                                       AS total_games,
                     COALESCE(SUM(buyin), 0)                      AS total_buyin,
                     COALESCE(SUM(rebuys), 0)                    AS total_rebuys,
                     COALESCE(SUM(buyin + (rebuys * buyin)), 0)  AS total_invested,
                     MAX(net)                                    AS biggest_win,
                     MIN(net)                                    AS biggest_loss
              FROM game_players
              WHERE username = ? AND tenant_id = ?
            )
            SELECT s.*,
                   p.balance                                 AS net_sum,
                   CASE
                     WHEN s.total_invested > 0
                       THEN ROUND(CAST(p.balance AS FLOAT) / s.total_invested * 100, 2)
                     ELSE 0
                   END AS roi
            FROM user_stats s
            JOIN players p
              ON p.username = ? AND p.tenant_id = ?
            """,
            (username, tenant_id, username, tenant_id)
        ).fetchone()

        if not stats:
            raise HTTPException(404, detail="No stats found for user.")

        win_count = db.execute(
            "SELECT COUNT(*) FROM games WHERE winner = ? AND amount > 0 AND tenant_id = ?",
            (username, tenant_id),
        ).fetchone()[0] or 0

        total_games = stats["total_games"]
        win_rate = round(win_count / total_games * 100, 1) if total_games else 0
        avg_profit = round(stats["net_sum"] / total_games, 1) if total_games else 0

        # Chart data
        rows = db.execute(
            """
            SELECT g.date, SUM(gp.net) AS daily_net
            FROM game_players gp
            JOIN games g ON g.id = gp.game_id AND g.tenant_id = gp.tenant_id
            WHERE gp.username = ? AND gp.tenant_id = ?
            GROUP BY g.date
            ORDER BY g.date
            """,
            (username, tenant_id),
        ).fetchall()

        dates = [r["date"] for r in rows]
        cumulative = []
        running = 0
        for r in rows:
            running += r["daily_net"]
            cumulative.append(running)

        # Recent sessions
        recent = db.execute(
            """
            SELECT g.date, gp.net AS net
            FROM game_players gp
            JOIN games g ON g.id = gp.game_id AND g.tenant_id = gp.tenant_id
            WHERE gp.username = ? AND gp.tenant_id = ?
            ORDER BY g.date DESC
            LIMIT 10
            """,
            (username, tenant_id),
        ).fetchall()

    except DatabaseError:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Unable to load dashboard data")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "username": username,
            "total_games": stats["total_games"],
            "total_buyin": stats["total_buyin"],
            "total_rebuys": stats["total_rebuys"],
            "total_invested": stats["total_invested"],
            "net_sum": stats["net_sum"],
            "avg_profit": avg_profit,
            "win_rate": win_rate,
            "roi": stats["roi"],
            "biggest_win": stats["biggest_win"],
            "biggest_loss": stats["biggest_loss"],
            "dates": dates,
            "cumulative": cumulative,
            "recent": recent,
        }
    )
