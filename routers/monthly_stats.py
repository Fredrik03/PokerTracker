from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from collections import defaultdict
from datetime import datetime
import calendar

from deps import get_current_user
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/monthly-stats")
def monthly_stats(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # ── 1) compute final‐week flag & countdown ────────────────────────────
    today = datetime.now()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    is_final_week = today.day > (days_in_month - 7)
    days_left = days_in_month - today.day + 1  # inclusive count

    with get_db() as db:
        current_month = db.execute(
            "SELECT strftime('%Y-%m', DATE('now'))"
        ).fetchone()[0]

        # ── existing: total games & money ────────────────────────────────
        total_games = db.execute("""
            SELECT COUNT(*) FROM games
            WHERE strftime('%Y-%m', date) = ?
        """, (current_month,)).fetchone()[0]

        total_money = db.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM games
            WHERE strftime('%Y-%m', date) = ?
        """, (current_month,)).fetchone()[0]

        # ── existing: biggest win ───────────────────────────────────────
        biggest_win_row = db.execute("""
            SELECT winner, MAX(amount) AS max_amount
            FROM games
            WHERE strftime('%Y-%m', date) = ?
        """, (current_month,)).fetchone()
        biggest_win = biggest_win_row["max_amount"] if biggest_win_row else 0
        biggest_winner = biggest_win_row["winner"] if biggest_win_row else "N/A"

        # ── existing: worst loss ────────────────────────────────────────
        worst_loss_row = db.execute("""
            SELECT username, MIN(net) AS min_net
            FROM game_players
            WHERE game_id IN (
                SELECT id FROM games WHERE strftime('%Y-%m', date) = ?
            )
        """, (current_month,)).fetchone()
        worst_loss = worst_loss_row["min_net"] if worst_loss_row else 0
        worst_loser = worst_loss_row["username"] if worst_loss_row else "N/A"

        # ── existing: aggregate per-player stats ────────────────────────
        player_rows = db.execute("""
            SELECT username, net, buyin, rebuys, game_id
            FROM game_players
            WHERE game_id IN (
                SELECT id FROM games WHERE strftime('%Y-%m', date) = ?
            )
        """, (current_month,)).fetchall()

        stats = defaultdict(lambda: {"net": 0, "buyin": 0, "rebuys": 0, "games": set()})
        for row in player_rows:
            u = row["username"]
            stats[u]["net"] += row["net"]
            stats[u]["buyin"] += row["buyin"] + row["rebuys"] * row["buyin"]
            stats[u]["rebuys"] += row["rebuys"]
            stats[u]["games"].add(row["game_id"])

        # ── existing: top earner & loser ────────────────────────────────
        top_earner = max(stats.items(), key=lambda x: x[1]["net"], default=("N/A", {"net": 0}))
        top_loser  = min(stats.items(), key=lambda x: x[1]["net"], default=("N/A", {"net": 0}))

        # ── existing: most rebuys ───────────────────────────────────────
        most_rebuys = ("N/A", {"rebuys": 0})
        for u, data in stats.items():
            if data["rebuys"] > most_rebuys[1]["rebuys"]:
                most_rebuys = (u, data)

        # ── existing: best ROI ─────────────────────────────────────────
        best_roi = max(
            ((u, round((v["net"] / v["buyin"] * 100), 2))
             for u, v in stats.items() if v["buyin"] > 0),
            key=lambda x: x[1], default=("N/A", 0.0)
        )

        # ── existing: most consistent (lowest abs net with ≥3 games) ──
        most_consistent = min(
            ((u, abs(v["net"])) for u, v in stats.items() if len(v["games"]) >= 3),
            key=lambda x: x[1], default=("N/A", 0.0)
        )

        # ── existing: player of the month scoring ──────────────────────
        def potm_score(item):
            u, v = item
            roi_pct = (round((v["net"] / v["buyin"] * 100), 2)
                       if v["buyin"] > 0 else 0)
            return (
                v["net"]
                + roi_pct * 2
                + len(v["games"]) * 5
                - v["rebuys"] * 2
            )

        potm = max(stats.items(), key=potm_score, default=("N/A", {}))

        # ── existing: comeback player (net>0 & ≥2 rebuys) ────────────
        comeback_player = max(
            ((u, v) for u, v in stats.items() if v["net"] > 0 and v["rebuys"] >= 2),
            key=lambda x: x[1]["net"],
            default=("N/A", {"net": 0})
        )

        # ── existing: most games played ───────────────────────────────
        most_games_player = max(
            stats.items(),
            key=lambda x: len(x[1]["games"]),
            default=("N/A", {"games": set()})
        )

        # ── top 5 monthly earners table (alias SUM(net) AS net) ───────
        top_monthly_earners = db.execute("""
            SELECT
              username,
              SUM(net) AS net
            FROM game_players
            WHERE game_id IN (
                SELECT id FROM games WHERE strftime('%Y-%m', date) = ?
            )
            GROUP BY username
            ORDER BY net DESC
            LIMIT 5
        """, (current_month,)).fetchall()

        # ── helper to fetch avatar path ───────────────────────────────
        def get_avatar(username):
            row = db.execute(
                "SELECT avatar_path FROM players WHERE username = ?", (username,)
            ).fetchone()
            return row["avatar_path"] if row and row["avatar_path"] else None

        # ── 2) shortlist top 3 by the same POTM score ──────────────────
        sorted_by_score = sorted(stats.items(), key=potm_score, reverse=True)
        top_three_raw = sorted_by_score[:3]
        top_three = [
            {
                "username": u,
                "net": v["net"],
                "avatar": get_avatar(u),
            }
            for u, v in top_three_raw
        ]
        # Store Player of the Month if it's the last day of the month and hasn't been stored yet
        if today.day == days_in_month and potm[0] != "N/A":
            existing = db.execute(
                "SELECT 1 FROM potm_history WHERE month = ?", (current_month,)
            ).fetchone()

            if not existing:
                db.execute("""
                           INSERT INTO potm_history (month, username, avatar_path)
                           VALUES (?, ?, ?)
                           """, (
                               current_month,
                               potm[0],
                               get_avatar(potm[0])
                           ))
                db.commit()

        # ── finally, render EVERYTHING ─────────────────────────────────
        return templates.TemplateResponse("stats.html", {
            "request": request,
            "monthly_ctx": {
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
                "player_of_month": potm[0],
                "comeback_user": comeback_player[0],
                "comeback_net": comeback_player[1]["net"],
                "most_games_user": most_games_player[0],
                "most_games_count": len(most_games_player[1]["games"]),
                "top_monthly_earners": top_monthly_earners,

                # avatars
                "player_of_month_avatar": get_avatar(potm[0]),
                "top_earner_avatar": get_avatar(top_earner[0]),
                "top_loser_avatar": get_avatar(top_loser[0]),
                "top_rebuyer_avatar": get_avatar(most_rebuys[0]),
                "roi_user_avatar": get_avatar(best_roi[0]),
                "most_consistent_avatar": get_avatar(most_consistent[0]),
                "comeback_avatar": get_avatar(comeback_player[0]),
                "most_games_avatar": get_avatar(most_games_player[0]),
                "biggest_win_avatar": get_avatar(biggest_winner),
                "worst_loss_avatar": get_avatar(worst_loser),

                # final week logic
                "is_final_week": is_final_week,
                "days_left": days_left,
                "top_three": top_three,
            }
        })

