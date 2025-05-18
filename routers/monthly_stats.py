from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from deps import get_current_user
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/monthly-stats")
def monthly_stats(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    with get_db() as db:
        current_month = db.execute("SELECT strftime('%Y-%m', DATE('now'))").fetchone()[0]

        # One game = one row
        total_games = db.execute("""
            SELECT COUNT(*) FROM games
            WHERE strftime('%Y-%m', date) = ?
        """, (current_month,)).fetchone()[0]

        # Winner net gain per game
        total_money = db.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM games
            WHERE strftime('%Y-%m', date) = ?
        """, (current_month,)).fetchone()[0]

        # ✅ Top earner (from game_players)
        top_earner_row = db.execute("""
            SELECT username, SUM(net) AS total_net
            FROM game_players
            WHERE game_id IN (
                SELECT id FROM games WHERE strftime('%Y-%m', date) = ?
            )
            GROUP BY username
            ORDER BY total_net DESC
            LIMIT 1
        """, (current_month,)).fetchone()

        top_earner = top_earner_row["username"] if top_earner_row else "N/A"
        top_earner_amount = top_earner_row["total_net"] if top_earner_row else 0

        # ✅ Top loser (lowest total net)
        top_loser_row = db.execute("""
            SELECT username, SUM(net) AS total_net
            FROM game_players
            WHERE game_id IN (
                SELECT id FROM games WHERE strftime('%Y-%m', date) = ?
            )
            GROUP BY username
            ORDER BY total_net ASC
            LIMIT 1
        """, (current_month,)).fetchone()

        top_loser = top_loser_row["username"] if top_loser_row else "N/A"
        top_loser_amount = top_loser_row["total_net"] if top_loser_row else 0

        # ✅ Average profit (winner-only, same as before)
        avg_profit_row = db.execute("""
            SELECT ROUND(AVG(amount), 2)
            FROM games
            WHERE strftime('%Y-%m', date) = ?
        """, (current_month,)).fetchone()

        avg_profit = avg_profit_row[0] if avg_profit_row else 0

        # ✅ Biggest single win
        biggest_win_row = db.execute("""
            SELECT winner, MAX(amount) AS max_amount
            FROM games
            WHERE strftime('%Y-%m', date) = ?
        """, (current_month,)).fetchone()

        biggest_win = biggest_win_row["max_amount"] if biggest_win_row else 0
        biggest_winner = biggest_win_row["winner"] if biggest_win_row else "N/A"

    return templates.TemplateResponse("monthly_stats.html", {
        "request": request,
        "total_games": total_games,
        "total_money": total_money,
        "top_earner": top_earner,
        "top_earner_amount": top_earner_amount,
        "top_loser": top_loser,
        "top_loser_amount": top_loser_amount,
        "avg_profit": avg_profit,
        "biggest_win": biggest_win,
        "biggest_winner": biggest_winner
    })

