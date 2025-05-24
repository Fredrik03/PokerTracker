from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from collections import defaultdict
from datetime import datetime
import calendar

from deps import get_current_user, tenant_required, get_tenant_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/stats", dependencies=[Depends(tenant_required)])
def stats(request: Request, db = Depends(get_tenant_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    today = datetime.now()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    is_final_week = today.day > (days_in_month - 7)
    days_left = days_in_month - today.day + 1
    current_month = today.strftime("%Y-%m")
    tenant_id = request.state.tenant_id

    # ── avatars helper ─────────────────────────────────────────────
    def get_avatar(username):
        if not username or username == "N/A":
            return None
        row = db.execute(
            "SELECT avatar_path FROM players WHERE username = ? AND tenant_id = ?", 
            (username, tenant_id)
        ).fetchone()
        return row["avatar_path"] if row and row["avatar_path"] else None

    # ── MONTHLY STATS ──────────────────────────────────────────────
    # fetch monthly games and players
    monthly_game_ids = [r["id"] for r in db.execute(
        "SELECT id FROM games WHERE strftime('%Y-%m', date)=? AND tenant_id = ?",
        (current_month, tenant_id),
    ).fetchall()]

    monthly_players = db.execute(
        "SELECT username, net, buyin, rebuys, game_id FROM game_players "
        "WHERE game_id IN ({seq}) AND tenant_id = ?".format(
            seq=",".join("?"*len(monthly_game_ids))
        ),
        tuple(monthly_game_ids + [tenant_id])
    ).fetchall() if monthly_game_ids else []

    # aggregate per-user
    mstats = defaultdict(lambda: {"net":0,"buyin":0,"rebuys":0,"games":set()})
    for r in monthly_players:
        u=r["username"]; mstats[u]["net"]+=r["net"]
        mstats[u]["buyin"]+=r["buyin"] + r["rebuys"]*r["buyin"]
        mstats[u]["rebuys"]+=r["rebuys"]; mstats[u]["games"].add(r["game_id"])
    # pickers
    def potm_score(item):
        u,v=item
        roi = (v["net"]/v["buyin"]*100) if v["buyin"]>0 else 0
        return v["net"] + roi*2 + len(v["games"])*5 - v["rebuys"]*2
    potm = max(mstats.items(), key=potm_score, default=("N/A",{}))
    top_three_raw = sorted(mstats.items(), key=potm_score, reverse=True)[:3]
    top_three = [{"username":u,"net":v["net"],"avatar":get_avatar(u)} for u,v in top_three_raw]

    monthly_ctx = {
        "total_games": len(monthly_game_ids),
        "total_money": db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM games WHERE strftime('%Y-%m',date)=? AND tenant_id = ?",
            (current_month, tenant_id),
        ).fetchone()[0],
        "biggest_win": db.execute(
            "SELECT MAX(amount) FROM games WHERE strftime('%Y-%m',date)=? AND tenant_id = ?",
            (current_month, tenant_id),
        ).fetchone()[0] or 0,
        "biggest_winner": (db.execute(
            "SELECT winner FROM games WHERE strftime('%Y-%m',date)=? AND tenant_id = ? ORDER BY amount DESC LIMIT 1",
            (current_month, tenant_id),
        ).fetchone() or {"winner": "N/A"})["winner"],
        "worst_loss": db.execute(
            "SELECT MIN(net) FROM game_players WHERE game_id IN ({seq}) AND tenant_id = ?".format(
                seq=",".join("?"*len(monthly_game_ids))
            ),
            tuple(monthly_game_ids + [tenant_id])
        ).fetchone()[0] or 0,
        "worst_loser": (db.execute(
            "SELECT username FROM game_players WHERE game_id IN ({seq}) AND tenant_id = ? ORDER BY net ASC LIMIT 1".format(
                seq=",".join("?"*len(monthly_game_ids))
            ),
            tuple(monthly_game_ids + [tenant_id])
        ).fetchone() or {"username": "N/A"})["username"],
        "top_earner": max(mstats.items(), key=lambda x:x[1]["net"], default=("N/A",{}))[0],
        "top_earner_amount": max(mstats.items(), key=lambda x:x[1]["net"], default=("",{"net":0}))[1]["net"],
        "top_loser": min(mstats.items(), key=lambda x:x[1]["net"], default=("N/A",{}))[0],
        "top_loser_amount": min(mstats.items(), key=lambda x:x[1]["net"], default=("",{"net":0}))[1]["net"],
        "top_rebuyer": max(mstats.items(), key=lambda x:x[1]["rebuys"], default=("N/A",{}))[0],
        "total_rebuys": max(mstats.items(), key=lambda x:x[1]["rebuys"], default=("",{"rebuys":0}))[1]["rebuys"],
        "best_roi": max(
            ((u,round(v["net"]/v["buyin"]*100,2)) for u,v in mstats.items() if v["buyin"]>0),
            key=lambda x:x[1], default=("N/A",0)
        )[1],
        "roi_user": max(
            ((u,round(v["net"]/v["buyin"]*100,2)) for u,v in mstats.items() if v["buyin"]>0),
            key=lambda x:x[1], default=("N/A",0)
        )[0],
        "most_consistent_user": min(
            ((u,abs(v["net"])) for u,v in mstats.items() if len(v["games"])>=3),
            key=lambda x:x[1], default=("N/A",0)
        )[0],
        "consistent_user_avg": min(
            ((u,abs(v["net"])) for u,v in mstats.items() if len(v["games"])>=3),
            key=lambda x:x[1], default=("N/A",0)
        )[1],
        "player_of_month": potm[0],
        "player_of_month_avatar": get_avatar(potm[0]),
        "comeback_user": max(
            ((u,v) for u,v in mstats.items() if v["net"]>0 and v["rebuys"]>=2),
            key=lambda x:x[1]["net"], default=("N/A",{"net":0})
        )[0],
        "comeback_net": max(
            ((u,v) for u,v in mstats.items() if v["net"]>0 and v["rebuys"]>=2),
            key=lambda x:x[1]["net"], default=("N/A",{"net":0})
        )[1]["net"],
        "most_games_user": max(mstats.items(), key=lambda x:len(x[1]["games"]), default=("N/A",{"games":set()}))[0],
        "most_games_count": len(max(mstats.items(), key=lambda x:len(x[1]["games"]), default=("",{"games":set()}))[1]["games"]),
        "top_monthly_earners": db.execute(
            "SELECT username, SUM(net) AS net FROM game_players WHERE game_id IN ({}) AND tenant_id = ? GROUP BY username ORDER BY net DESC LIMIT 5".format(
                ",".join("?"*len(monthly_game_ids))
            ),
            tuple(monthly_game_ids + [tenant_id])
        ).fetchall(),
        "is_final_week": is_final_week,
        "days_left": days_left,
        "top_three": top_three,
    }

    # Add avatars for monthly context
    monthly_ctx.update({
        "biggest_winner_avatar": get_avatar(monthly_ctx["biggest_winner"]),
        "worst_loser_avatar": get_avatar(monthly_ctx["worst_loser"]),
        "top_earner_avatar": get_avatar(monthly_ctx["top_earner"]),
        "top_loser_avatar": get_avatar(monthly_ctx["top_loser"]),
        "roi_user_avatar": get_avatar(monthly_ctx["roi_user"]),
        "most_consistent_avatar": get_avatar(monthly_ctx["most_consistent_user"]),
        "comeback_avatar": get_avatar(monthly_ctx["comeback_user"]),
        "top_rebuyer_avatar": get_avatar(monthly_ctx["top_rebuyer"])
    })

    # Format monthly earners
    monthly_earners = []
    for row in monthly_ctx["top_monthly_earners"]:
        monthly_earners.append({
            "username": row["username"],
            "net": row["net"],
            "avatar": get_avatar(row["username"]),
            "initial": row["username"][0].upper() if row["username"] else "?"
        })
    monthly_ctx["top_monthly_earners"] = monthly_earners

    # ── GLOBAL STATS ────────────────────────────────────────────────
    gstats = defaultdict(lambda: {"net":0,"buyin":0,"rebuys":0,"games":set()})
    all_players = db.execute(
        "SELECT username, net, buyin, rebuys, game_id FROM game_players WHERE tenant_id = ?",
        (tenant_id,)
    ).fetchall()
    for r in all_players:
        u=r["username"]; gstats[u]["net"]+=r["net"]
        gstats[u]["buyin"]+=r["buyin"]+r["rebuys"]*r["buyin"]
        gstats[u]["rebuys"]+=r["rebuys"]; gstats[u]["games"].add(r["game_id"])

    global_ctx = {
        "total_games": db.execute(
            "SELECT COUNT(*) FROM games WHERE tenant_id = ?",
            (tenant_id,)
        ).fetchone()[0],
        "total_money": db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM games WHERE tenant_id = ?",
            (tenant_id,)
        ).fetchone()[0],
        "biggest_win": db.execute(
            "SELECT MAX(amount) FROM games WHERE tenant_id = ?",
            (tenant_id,)
        ).fetchone()[0] or 0,
        "biggest_winner": (db.execute(
            "SELECT winner FROM games WHERE tenant_id = ? ORDER BY amount DESC LIMIT 1",
            (tenant_id,)
        ).fetchone() or {"winner": "N/A"})["winner"],
        "worst_loss": db.execute(
            "SELECT MIN(net) FROM game_players WHERE tenant_id = ?",
            (tenant_id,)
        ).fetchone()[0] or 0,
        "worst_loser": (db.execute(
            "SELECT username FROM game_players WHERE tenant_id = ? ORDER BY net ASC LIMIT 1",
            (tenant_id,)
        ).fetchone() or {"username": "N/A"})["username"],
        "top_earner": (max(gstats.items(), key=lambda x:x[1]["net"], default=("N/A",{})))[0],
        "top_earner_amount": (max(gstats.items(), key=lambda x:x[1]["net"], default=("",{"net":0})))[1]["net"],
        "top_loser": (min(gstats.items(), key=lambda x:x[1]["net"], default=("N/A",{})))[0],
        "top_loser_amount": (min(gstats.items(), key=lambda x:x[1]["net"], default=("",{"net":0})))[1]["net"],
        "top_rebuyer": (max(gstats.items(), key=lambda x:x[1]["rebuys"], default=("N/A",{})))[0],
        "total_rebuys": (max(gstats.items(), key=lambda x:x[1]["rebuys"], default=("",{"rebuys":0})))[1]["rebuys"],
        "best_roi": (max(
            ((u,round(v["net"]/v["buyin"]*100,2)) for u,v in gstats.items() if v["buyin"]>0),
            key=lambda x:x[1], default=("N/A",0)
        ))[1],
        "roi_user": (max(
            ((u,round(v["net"]/v["buyin"]*100,2)) for u,v in gstats.items() if v["buyin"]>0),
            key=lambda x:x[1], default=("N/A",0)
        ))[0],
        "most_consistent_user": (min(
            ((u,abs(v["net"])) for u,v in gstats.items() if len(v["games"])>=3),
            key=lambda x:x[1], default=("N/A",0)
        ))[0],
        "consistent_user_avg": (min(
            ((u,abs(v["net"])) for u,v in gstats.items() if len(v["games"])>=3),
            key=lambda x:x[1], default=("N/A",0)
        ))[1],
        "comeback_user": (max(
            ((u,v) for u,v in gstats.items() if v["net"]>0 and v["rebuys"]>=2),
            key=lambda x:x[1]["net"], default=("N/A",{"net":0})
        ))[0],
        "comeback_net": (max(
            ((u,v) for u,v in gstats.items() if v["net"]>0 and v["rebuys"]>=2),
            key=lambda x:x[1]["net"], default=("N/A",{"net":0})
        ))[1]["net"],
        "most_games_user": (max(gstats.items(), key=lambda x:len(x[1]["games"]), default=("N/A",{"games":set()})))[0],
        "most_games_count": len((max(gstats.items(), key=lambda x:len(x[1]["games"]), default=("",{"games":set()})))[1]["games"])
    }

    # Add avatars for global context
    global_ctx.update({
        "biggest_winner_avatar": get_avatar(global_ctx["biggest_winner"]),
        "worst_loser_avatar": get_avatar(global_ctx["worst_loser"]),
        "top_earner_avatar": get_avatar(global_ctx["top_earner"]),
        "top_loser_avatar": get_avatar(global_ctx["top_loser"]),
        "roi_user_avatar": get_avatar(global_ctx["roi_user"]),
        "most_consistent_avatar": get_avatar(global_ctx["most_consistent_user"]),
        "comeback_avatar": get_avatar(global_ctx["comeback_user"]),
        "top_rebuyer_avatar": get_avatar(global_ctx["top_rebuyer"])
    })

    # Format global earners with avatars and initials
    global_earners = []
    for row in db.execute(
        "SELECT username, SUM(net) AS net FROM game_players WHERE tenant_id = ? GROUP BY username ORDER BY net DESC LIMIT 5",
        (tenant_id,)
    ).fetchall():
        global_earners.append({
            "username": row["username"],
            "net": row["net"],
            "avatar": get_avatar(row["username"]),
            "initial": row["username"][0].upper() if row["username"] else "?"
        })
    global_ctx["top_global_earners"] = global_earners

    # Format POTM history with avatars
    potm_history = []
    for row in db.execute(
        "SELECT month, username, avatar_path FROM potm_history WHERE tenant_id = ? ORDER BY month DESC",
        (tenant_id,)
    ).fetchall():
        potm_history.append({
            "month": row["month"],
            "username": row["username"],
            "avatar": row["avatar_path"] or get_avatar(row["username"]),
            "initial": row["username"][0].upper() if row["username"] else "?"
        })
    global_ctx["potm_history"] = potm_history

    # Helper function to format username initials
    def format_username_initial(username):
        if username and username != "N/A":
            return username[0].upper()
        return "?"

    # Add formatted initials for both contexts
    for ctx in [monthly_ctx, global_ctx]:
        ctx["formatted_initials"] = {
            key: format_username_initial(ctx.get(key, ""))
            for key in [
                "biggest_winner", "worst_loser", "top_earner", "top_loser",
                "roi_user", "most_consistent_user", "comeback_user", "top_rebuyer",
                "most_games_user"
            ]
        }

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "monthly": monthly_ctx,
        "global": global_ctx
    })