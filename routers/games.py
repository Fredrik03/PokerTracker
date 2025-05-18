from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from config import BUYIN_DEFAULT
from db import get_db
from deps import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/add-game")
def add_game_form(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["is_admin"] != 1:
        raise HTTPException(status_code=403, detail="Admins only")

    # load all players (no filtering)
    with get_db() as db:
        all_players = db.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()

    return templates.TemplateResponse(
        "add_game.html",
        {
            "request":     request,
            "all_players": all_players,
            "buyin":       BUYIN_DEFAULT,
        }
    )


@router.post("/add-game")
async def add_game(request: Request):
    user = get_current_user(request)
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403, detail="Admins only")

    form = await request.form()
    date = form.get("date") or ""
    buyin = int(form.get("buyin", BUYIN_DEFAULT))

    total_rebuys = 0
    winner = None
    winner_net = 0
    highest_cashout = -1

    with get_db() as db:
        # Create the game row early so we can link to it
        result = db.execute(
            "INSERT INTO games (date, winner, amount, rebuys) VALUES (?, ?, ?, ?)",
            (date, "", 0, 0)  # Temporary values for winner + amount
        )
        game_id = result.lastrowid

        players = db.execute("SELECT username FROM players").fetchall()

        for r in players:
            username = r["username"]
            if form.get(f"play_{username}"):
                cashout = int(form.get(f"amount_{username}", 0))
                rebuys = int(form.get(f"rebuys_{username}", 0))
                cost = buyin * (1 + rebuys)
                net = cashout - cost

                total_rebuys += rebuys

                # Auto-select winner: highest cashout
                if cashout > highest_cashout:
                    highest_cashout = cashout
                    winner = username
                    winner_net = net

                db.execute("""
                    INSERT INTO game_players (game_id, username, buyin, rebuys, cashout, net)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (game_id, username, buyin, rebuys, cashout, net))

                db.execute("""
                    UPDATE players SET balance = balance + ? WHERE username = ?
                """, (net, username))

        # Update the games row with real winner and stats
        db.execute("""
            UPDATE games SET winner = ?, amount = ?, rebuys = ? WHERE id = ?
        """, (winner, winner_net, total_rebuys, game_id))

        db.commit()

    return RedirectResponse("/admin", status_code=302)


