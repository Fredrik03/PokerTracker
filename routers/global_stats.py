from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from collections import defaultdict  # ← ADD THIS
from datetime import datetime


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
        # ── all-time total games & money ─
        total_games = db.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        total_money = db.execute("SELECT COALESCE(SUM(amount), 0) FROM games").fetchone()[0]

        # ── biggest win and worst loss ──
        biggest_win_row = db.execute("SELECT winner, MAX(amount) AS max_amount FROM games").fetchone()
        worst_loss_row = db.execute("SELECT username, MIN(net) AS min_net FROM game_players").fetchone()

        biggest_win = biggest_win_row["max_amount"] if biggest_win_row else 0
        biggest_winner = biggest_win_row["winner"] if biggest_win_row else "N/A"
        worst_loss = worst_loss_row["min_net"] if worst_loss_row else 0
        worst_loser = worst_loss_row["username"] if worst_loss_row else "N/A"

        # ── aggregate stats ──
        player_rows = db.execute("SELECT username, net, buyin, rebuys, game_id FROM game_players").fetchall()
        stats = defaultdict(lambda: {"net": 0, "buyin": 0, "rebuys": 0, "games": set()})
        for row in player_rows:
            u = row["username"]
            stats[u]["net"] += row["net"]
            stats[u]["buyin"] += row["buyin"] + row["rebuys"] * row["buyin"]
            stats[u]["rebuys"] += row["rebuys"]
            stats[u]["games"].add(row["game_id"])

        top_earner = max(stats.items(), key=lambda x: x[1]["net"], default=("N/A", {"net": 0}))
        top_loser = min(stats.items(), key=lambda x: x[1]["net"], default=("N/A", {"net": 0}))
        most_rebuys = max(stats.items(), key=lambda x: x[1]["rebuys"], default=("N/A", {"rebuys": 0}))
        best_roi = max(
            ((u, round((v["net"] / v["buyin"] * 100), 2)) for u, v in stats.items() if v["buyin"] > 0),
            key=lambda x: x[1], default=("N/A", 0.0)
        )
        most_consistent = min(
            ((u, abs(v["net"])) for u, v in stats.items() if len(v["games"]) >= 3),
            key=lambda x: x[1], default=("N/A", 0.0)
        )
        comeback_player = max(
            ((u, v) for u, v in stats.items() if v["net"] > 0 and v["rebuys"] >= 2),
            key=lambda x: x[1]["net"], default=("N/A", {"net": 0})
        )
        most_games_player = max(
            stats.items(), key=lambda x: len(x[1]["games"]), default=("N/A", {"games": set()})
        )

        # ── top 5 all-time earners ──
        top_global_earners = db.execute("""
            SELECT username, SUM(net) AS net
            FROM game_players
            GROUP BY username
            ORDER BY net DESC
            LIMIT 5
        """).fetchall()

        # ── player of the month history ──
        potm_history = db.execute("""
            SELECT month, username, avatar_path FROM potm_history
            ORDER BY month DESC
        """).fetchall()

        # ── new global stats additions ──
        unique_winners = db.execute("SELECT COUNT(DISTINCT winner) FROM games").fetchone()[0]

        top_player_row = db.execute("""
            SELECT winner, COUNT(*) AS wins
            FROM games
            GROUP BY winner
            ORDER BY wins DESC
            LIMIT 1
        """).fetchone()
        top_player = top_player_row["winner"] if top_player_row else "N/A"

        top_players = db.execute("""
            SELECT winner, SUM(amount) AS total_won
            FROM games
            GROUP BY winner
            ORDER BY total_won DESC
            LIMIT 5
        """).fetchall()

        def get_avatar(username):
            row = db.execute("SELECT avatar_path FROM players WHERE username = ?", (username,)).fetchone()
            return row["avatar_path"] if row and row["avatar_path"] else None

        return templates.TemplateResponse("stats.html", {
            "request": request,
            "global_ctx": {
                "total_games": total_games,
                "total_money": total_money,
                "biggest_win": biggest_win,
                "biggest_winner": biggest_winner,
                "worst_loss": worst_loss,
                "worst_loser": worst_loser,
                "top_earner": top_earner[0],
                "top_earner_amount": top_earner[1]["net"],
                "top_loser": top_loser[0],
                "top_loser_amount": top_loser[1]["net"],
                "top_rebuyer": most_rebuys[0],
                "total_rebuys": most_rebuys[1]["rebuys"],
                "best_roi": best_roi[1],
                "roi_user": best_roi[0],
                "most_consistent_user": most_consistent[0],
                "consistent_user_avg": most_consistent[1],
                "comeback_user": comeback_player[0],
                "comeback_net": comeback_player[1]["net"],
                "most_games_user": most_games_player[0],
                "most_games_count": len(most_games_player[1]["games"]),
                "top_global_earners": top_global_earners,
                "potm_history": potm_history,
                "unique_winners": unique_winners,
                "top_player": top_player,
                "top_players": top_players,
                "top_earner_avatar": get_avatar(top_earner[0]),
                "top_loser_avatar": get_avatar(top_loser[0]),
                "top_rebuyer_avatar": get_avatar(most_rebuys[0]),
                "roi_user_avatar": get_avatar(best_roi[0]),
                "most_consistent_avatar": get_avatar(most_consistent[0]),
                "comeback_avatar": get_avatar(comeback_player[0]),
                "most_games_avatar": get_avatar(most_games_player[0]),
                "biggest_win_avatar": get_avatar(biggest_winner),
                "worst_loss_avatar": get_avatar(worst_loser),
            }
        })


