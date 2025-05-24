from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from deps import get_current_user, tenant_required, get_tenant_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get(
    "/leaderboard",
    response_class=HTMLResponse,
    dependencies=[Depends(tenant_required)]
)
async def leaderboard(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_tenant_db)
):
    # 1) Auth guard
    if not current_user:
        return RedirectResponse("/login", status_code=302)

    tenant_id = request.state.tenant_id

    # 2) Sanitize sort param against an allowlist
    sort_key = request.query_params.get("sort", "balance")
    order_map = {
        "username": "p.username ASC",
        "games": "games_played DESC",
        "rebuys": "total_rebuys DESC",
        "balance": "p.balance DESC",
    }
    order_by = order_map.get(sort_key, order_map["balance"])

    try:
        # 3) Secure query — tenant_id explicitly required on both p and gp
        query = f"""
            SELECT 
                p.username,
                p.balance,
                p.avatar_path,
                COUNT(DISTINCT gp.game_id)       AS games_played,
                COALESCE(SUM(gp.rebuys), 0)      AS total_rebuys
            FROM players p
            LEFT JOIN game_players gp 
              ON p.username = gp.username
             AND p.tenant_id = gp.tenant_id
             AND gp.tenant_id = ?
            WHERE p.tenant_id = ?
            GROUP BY p.username, p.balance, p.avatar_path
            ORDER BY {order_by}
        """
        players = db.execute(query, (tenant_id, tenant_id)).fetchall()
    except Exception as e:
        raise HTTPException(500, f"Unable to load leaderboard: {str(e)}")

    return templates.TemplateResponse(
        "leaderboard.html",
        {
            "request": request,
            "players": players,
            "current_sort": sort_key,
        }
    )
