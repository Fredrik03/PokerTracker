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

    # load all players
    with get_db() as db:
        all_players = db.execute("SELECT username FROM players").fetchall()

    # render with exactly the names your template expects
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
        raise HTTPException(403, "Admins only")

    form = await request.form()
    date  = form.get("date") or ""
    buyin = int(form.get("buyin", BUYIN_DEFAULT))

    with get_db() as db:
        players = db.execute("SELECT username FROM players").fetchall()
        for r in players:
            u = r["username"]
            if form.get(f"play_{u}"):
                cashout = int(form.get(f"amount_{u}", 0))
                rebuys  = int(form.get(f"rebuys_{u}",  0))
                # total cost = buyin × (1 + rebuys)
                cost    = buyin * (1 + rebuys)
                net     = cashout - cost

                db.execute(
                  "INSERT INTO games (date, winner, amount, rebuys) VALUES (?, ?, ?, ?)",
                  (date, u, net, rebuys)
                )
                db.execute(
                  "UPDATE players SET balance = balance + ? WHERE username = ?",
                  (net, u)
                )
        db.commit()

    return RedirectResponse("/admin", status_code=302)

