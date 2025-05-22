from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from deps import get_current_user
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    # 1) auth guard
    if not current_user:
        return RedirectResponse("/login", status_code=302)

    # 2) sanitize sort param against an allowlist
    sort_key = request.query_params.get("sort", "balance")
    order_map = {
        "username":    "p.username ASC",
        "games":       "games_played DESC",
        "rebuys":      "total_rebuys DESC",
        "balance":     "p.balance DESC",
    }
    order_by = order_map.get(sort_key, order_map["balance"])

    # 3) safe to interpolate because order_by only comes from our allowlist
    with get_db() as conn:
        players = conn.execute(f"""
            SELECT 
                p.username,
                p.balance,
                p.avatar_path,
                COUNT(DISTINCT gp.game_id)       AS games_played,
                COALESCE(SUM(gp.rebuys), 0)      AS total_rebuys
            FROM players p
            LEFT JOIN game_players gp ON p.username = gp.username
            GROUP BY p.username, p.balance, p.avatar_path
            ORDER BY {order_by}
        """).fetchall()

    return templates.TemplateResponse(
        "leaderboard.html",
        {
            "request":      request,
            "players":      players,
            "current_sort": sort_key,
        }
    )
