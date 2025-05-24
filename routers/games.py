from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import RedirectResponse
from datetime import datetime
import re
from urllib.parse import urlencode
from datetime import date

from config import BUYIN_DEFAULT
from deps import get_current_user, tenant_required, get_tenant_db, generate_csrf, verify_csrf
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
delim_limiter = Limiter(key_func=get_remote_address)

DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
INT_PATTERN = re.compile(r'^\d+$')


def redirect_with_error(msg: str):
    params = urlencode({"error": msg})
    return RedirectResponse(f"/admin?{params}", status_code=303)


@router.post(
    "/add-game",
    dependencies=[Depends(verify_csrf), Depends(tenant_required)]
)
@delim_limiter.limit("3/minute")
async def add_game(
    request: Request,
    date: str = Form(...),
    buyin: str = Form(str(BUYIN_DEFAULT)),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_tenant_db)
):
    if not current_user or current_user["is_admin"] != 1:
        raise HTTPException(status_code=403, detail="Admins only")

    tenant_id = request.state.tenant_id

    if not DATE_PATTERN.match(date):
        return redirect_with_error("Invalid date format. Use YYYY-MM-DD.")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return redirect_with_error("Invalid or out-of-range date.")

    if not INT_PATTERN.match(buyin):
        return redirect_with_error("Invalid buy-in amount.")
    buyin_val = int(buyin)
    if buyin_val <= 0:
        return redirect_with_error("Buy-in must be a positive number.")

    form = await request.form()
    total_rebuys = 0
    total_cashout = 0
    selected = []

    players = [r["username"] for r in db.execute(
        "SELECT username FROM players WHERE tenant_id = ?",
        (tenant_id,)
    ).fetchall()]

    for username in players:
        if form.get(f"play_{username}"):
            cash_str = form.get(f"amount_{username}", "0")
            reb_str = form.get(f"rebuys_{username}", "0")
            if not INT_PATTERN.match(cash_str) or not INT_PATTERN.match(reb_str):
                return redirect_with_error("Invalid numeric input for cash-out or rebuys.")
            cash = int(cash_str)
            rebuys = int(reb_str)
            if cash < 0 or rebuys < 0:
                return redirect_with_error("Cash-out and rebuys must be non-negative.")
            selected.append((username, cash, rebuys))
            total_rebuys += rebuys
            total_cashout += cash

    if not selected:
        return redirect_with_error("Select at least one player to add a game.")

    expected_total = buyin_val * len(selected) + buyin_val * total_rebuys
    if total_cashout > expected_total:
        return redirect_with_error(
            f"Total cash-out {total_cashout} exceeds allowed max {expected_total}."
        )

    cur = db.execute(
        "INSERT INTO games (date, winner, amount, rebuys, buyin, tenant_id) VALUES (?, ?, ?, ?, ?, ?)",
        (date, "", 0, total_rebuys, buyin_val, tenant_id)
    )
    game_id = cur.lastrowid

    winner = None
    highest_gain = float('-inf')
    for usern, cash, rebuys in selected:
        cost = buyin_val * (1 + rebuys)
        net = cash - cost
        if net > highest_gain:
            highest_gain = net
            winner = usern

        db.execute(
            "INSERT INTO game_players (game_id, username, buyin, rebuys, cashout, net, tenant_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (game_id, usern, buyin_val, rebuys, cash, net, tenant_id)
        )
        db.execute(
            "UPDATE players SET balance = balance + ? WHERE username = ? AND tenant_id = ?",
            (net, usern, tenant_id)
        )

    db.execute(
        "UPDATE games SET winner = ?, amount = ? WHERE id = ? AND tenant_id = ?",
        (winner, highest_gain, game_id, tenant_id)
    )
    db.commit()

    return RedirectResponse("/admin?msg=Game+added+successfully", status_code=302)
