from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import re

from config import BUYIN_DEFAULT
from db import get_db
from deps import get_current_user, generate_csrf, verify_csrf
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
templates = Jinja2Templates(directory="templates")
# rate limiter: 3 game submissions per minute per IP
limiter = Limiter(key_func=get_remote_address)

DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
INT_PATTERN = re.compile(r'^\d+$')

@router.get("/add-game", dependencies=[Depends(generate_csrf)])
def add_game_form(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["is_admin"] != 1:
        raise HTTPException(status_code=403, detail="Admins only")

    with get_db() as db:
        all_players = db.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()

    return templates.TemplateResponse(
        "add_game.html",
        {
            "request": request,
            "all_players": all_players,
            "buyin": BUYIN_DEFAULT,
            "csrf_token": request.session.get("csrf_token"),
        }
    )

@router.post("/add-game", dependencies=[Depends(verify_csrf)])
@limiter.limit("3/minute")
async def add_game(request: Request,
                   date: str = Form(...),
                   buyin: str = Form(str(BUYIN_DEFAULT))):
    user = get_current_user(request)
    if not user or user["is_admin"] != 1:
        raise HTTPException(status_code=403, detail="Admins only")

    # Validate date
    if not DATE_PATTERN.match(date):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date out of range.")

    # Validate buyin
    if not INT_PATTERN.match(buyin):
        raise HTTPException(status_code=400, detail="Invalid buy-in amount.")
    buyin_val = int(buyin)
    if buyin_val <= 0:
        raise HTTPException(status_code=400, detail="Buy-in must be positive.")

    form = await request.form()
    total_rebuys = 0
    total_cashout = 0
    selected = []

    with get_db() as db:
        players = [r["username"] for r in db.execute("SELECT username FROM players").fetchall()]

        for username in players:
            if form.get(f"play_{username}"):
                # sanitize numeric inputs
                cash_str = form.get(f"amount_{username}", "0")
                reb_str = form.get(f"rebuys_{username}", "0")
                if not INT_PATTERN.match(cash_str) or not INT_PATTERN.match(reb_str):
                    raise HTTPException(status_code=400, detail="Invalid numeric fields.")
                cash = int(cash_str)
                rebuys = int(reb_str)
                if cash < 0 or rebuys < 0:
                    raise HTTPException(status_code=400, detail="Cash-out and rebuys must be non-negative.")
                selected.append((username, cash, rebuys))
                total_rebuys += rebuys
                total_cashout += cash

        if not selected:
            raise HTTPException(status_code=400, detail="Select at least one player.")

        expected_total = buyin_val * len(selected) + buyin_val * total_rebuys
        if total_cashout > expected_total:
            raise HTTPException(
                status_code=400,
                detail=(f"Total cash-out {total_cashout} exceeds max {expected_total}.")
            )

        # Insert game
        cur = db.execute(
            "INSERT INTO games (date, winner, amount, rebuys, buyin) VALUES (?, ?, ?, ?, ?)",
            (date, "", 0, total_rebuys, buyin_val)
        )
        game_id = cur.lastrowid

        # Determine winner
        winner = None
        highest = -1
        for usern, cash, rebuys in selected:
            cost = buyin_val * (1 + rebuys)
            net = cash - cost
            if cash > highest:
                highest = cash
                winner = usern
            # insert and update
            db.execute(
                "INSERT INTO game_players (game_id, username, buyin, rebuys, cashout, net) VALUES (?, ?, ?, ?, ?, ?)",
                (game_id, usern, buyin_val, rebuys, cash, net)
            )
            db.execute(
                "UPDATE players SET balance = balance + ? WHERE username = ?",
                (net, usern)
            )

        # finalize game record
        db.execute(
            "UPDATE games SET winner = ?, amount = ? WHERE id = ?",
            (winner, highest - (buyin_val * (1 + next(r for r in selected if r[0]==winner)[2])), game_id)
        )
        db.commit()

    return RedirectResponse("/admin", status_code=302)
