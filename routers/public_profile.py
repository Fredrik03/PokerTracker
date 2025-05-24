from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlite3 import DatabaseError

from deps import tenant_required, get_tenant_db
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/player/{username}", response_class=HTMLResponse, dependencies=[Depends(tenant_required)])
def public_profile(request: Request, username: str, db = Depends(get_tenant_db)):
    tenant_id = request.state.tenant_id
    try:
        # Verify player exists in this tenant
        player = db.execute(
            "SELECT username, avatar_path FROM players WHERE username = ? AND tenant_id = ?",
            (username, tenant_id)
        ).fetchone()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        # Aggregate stats for the user within tenant
        stats = db.execute(
            """
            WITH user_stats AS (
                SELECT 
                    COUNT(*) AS total_games,
                    COALESCE(SUM(gp.buyin), 0) AS total_buyin,
                    COALESCE(SUM(gp.rebuys), 0) AS total_rebuys,
                    COALESCE(SUM(gp.buyin + (gp.rebuys * gp.buyin)), 0) AS total_invested,
                    MAX(gp.net) AS biggest_win,
                    MIN(gp.net) AS biggest_loss
                FROM game_players gp
                WHERE gp.username = ? AND gp.tenant_id = ?
            )
            SELECT 
                s.*,
                p.balance AS net_sum,
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

        # Win rate calculation
        win_count = db.execute(
            "SELECT COUNT(*) FROM games WHERE winner = ? AND amount > 0 AND tenant_id = ?",
            (username, tenant_id)
        ).fetchone()[0] or 0
        total_games = stats["total_games"]
        win_rate = round(win_count / total_games * 100, 1) if total_games else 0
        avg_profit = round(stats["net_sum"] / total_games, 1) if total_games else 0

        # Cumulative progress chart data
        rows = db.execute(
            """
            SELECT g.date, SUM(gp.net) AS daily_net
            FROM game_players gp
            JOIN games g
              ON g.id = gp.game_id AND g.tenant_id = gp.tenant_id
            WHERE gp.username = ? AND gp.tenant_id = ?
            GROUP BY g.date
            ORDER BY g.date
            """,
            (username, tenant_id)
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
            JOIN games g
              ON g.id = gp.game_id AND g.tenant_id = gp.tenant_id
            WHERE gp.username = ? AND gp.tenant_id = ?
            ORDER BY g.date DESC
            LIMIT 10
            """,
            (username, tenant_id)
        ).fetchall()

    except DatabaseError:
        raise HTTPException(status_code=500, detail="Unable to load profile data")

    return templates.TemplateResponse(
        "public_dashboard.html",
        {
            "request": request,
            "username": player["username"],
            "avatar_path": player.get("avatar_path"),
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
        }
    )
