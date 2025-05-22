from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from deps import get_current_user
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/player/{username}", response_class=HTMLResponse)
async def public_profile(
    username: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    # 1) Auth guard
    if not current_user:
        return RedirectResponse("/login", status_code=302)

    with get_db() as conn:
        # 2) Fetch player record
        player = conn.execute(
            "SELECT username, balance, avatar_path FROM players WHERE username = ?",
            (username,),
        ).fetchone()

        if not player:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "message": "Player not found"},
                status_code=404,
            )

        # 3) Fetch games for this player
        rows = conn.execute(
            """
            SELECT g.date, gp.net
              FROM game_players gp
              JOIN games g ON g.id = gp.game_id
             WHERE gp.username = ?
             ORDER BY g.date DESC
            """,
            (username,),
        ).fetchall()

    # 4) Compute stats
    total_games      = len(rows)
    net_sum          = sum(r["net"] for r in rows) if rows else 0
    avg_profit       = round(net_sum / total_games, 1) if total_games else 0
    profitable_count = sum(1 for r in rows if r["net"] > 0)
    win_rate         = round(profitable_count / total_games * 100, 1) if total_games else 0

    # 5) Build cumulative series (chronological)
    cumulative = []
    dates      = []
    running    = 0
    for game in reversed(rows):
        running += game["net"]
        cumulative.append(running)
        dates.append(game["date"])

    # 6) Recent 5 sessions
    recent = rows[:5]

    return templates.TemplateResponse(
        "public_dashboard.html",
        {
            "request":     request,
            "username":    player["username"],
            "avatar_path": player["avatar_path"],
            "total_games": total_games,
            "net_sum":     net_sum,
            "avg_profit":  avg_profit,
            "win_rate":    win_rate,
            "recent":      recent,
            "dates":       dates,
            "cumulative":  cumulative,
        },
    )
