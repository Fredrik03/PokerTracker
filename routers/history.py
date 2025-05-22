# routers/history.py
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlite3 import DatabaseError

from deps import get_current_user, generate_csrf, verify_csrf
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get(
    "/history",
    name="history_list",
    response_class=HTMLResponse,
    dependencies=[Depends(generate_csrf)]
)
def history(request: Request, current_user=Depends(get_current_user)):
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    try:
        with get_db() as db:
            games = db.execute(
                "SELECT id, date, winner, amount FROM games ORDER BY date DESC"
            ).fetchall()
    except DatabaseError:
        raise HTTPException(500, "Unable to load game history")

    return templates.TemplateResponse(
        "history.html",
        {
            "request":    request,
            "games":      games,
            "csrf_token": request.session.get("csrf_token"),
        }
    )


@router.get(
    "/history/{game_id}",
    name="history_detail",
    response_class=HTMLResponse,
    dependencies=[Depends(generate_csrf)]
)
def game_detail(request: Request, game_id: int, current_user=Depends(get_current_user)):
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    try:
        with get_db() as db:
            game = db.execute(
                "SELECT id, date, buyin FROM games WHERE id = ?",
                (game_id,)
            ).fetchone()
            if not game:
                raise HTTPException(404, "Game not found")

            players = db.execute(
                """
                SELECT gp.username, p.avatar_path, gp.net, gp.rebuys
                  FROM game_players gp
                  JOIN players p ON p.username = gp.username
                 WHERE gp.game_id = ?
                """,
                (game_id,)
            ).fetchall()
    except DatabaseError:
        raise HTTPException(500, "Unable to load game details")

    # sqlite3.Row does not implement .get()
    is_admin = bool(current_user["is_admin"])

    return templates.TemplateResponse(
        "game_detail.html",
        {
            "request":    request,
            "game":       game,
            "players":    players,
            "is_admin":   is_admin,
            "csrf_token": request.session.get("csrf_token"),
        }
    )


@router.post(
    "/admin/update-player-amount",
    name="admin_update_amount",
    dependencies=[Depends(verify_csrf)]
)
def update_player_amount(
    request: Request,
    game_id:  int    = Form(...),
    username: str    = Form(...),
    cashout:  int    = Form(...),
    rebuys:   int    = Form(...),
    current_user=Depends(get_current_user)
):
    # Guard: only admins
    if not current_user or not bool(current_user["is_admin"]):
        raise HTTPException(403, "Not authorized")

    try:
        with get_db() as db:
            prev = db.execute(
                "SELECT net FROM game_players WHERE game_id = ? AND username = ?",
                (game_id, username)
            ).fetchone()
            if not prev:
                raise HTTPException(404, "Player not in this game")
            old_net = prev["net"]

            game = db.execute(
                "SELECT buyin FROM games WHERE id = ?", (game_id,)
            ).fetchone()
            if not game:
                raise HTTPException(404, "Game not found")
            buyin = game["buyin"]

            new_net = cashout - buyin * (1 + rebuys)
            db.execute(
                """
                UPDATE game_players
                   SET cashout = ?, rebuys = ?, net = ?
                 WHERE game_id = ? AND username = ?
                """,
                (cashout, rebuys, new_net, game_id, username)
            )
            db.execute(
                "UPDATE players SET balance = balance + ? WHERE username = ?",
                (new_net - old_net, username)
            )
            db.execute(
                """
                UPDATE games
                   SET rebuys = (
                       SELECT SUM(rebuys) FROM game_players WHERE game_id = ?
                   )
                 WHERE id = ?
                """,
                (game_id, game_id)
            )
            db.execute(
                """
                INSERT INTO admin_log (actor, action, target, timestamp)
                     VALUES (?, ?, ?, datetime('now'))
                """,
                (
                    current_user["username"],
                    f"Updated game {game_id}: {username} → cashout={cashout}, rebuys={rebuys}, net={new_net}",
                    username
                )
            )
            db.commit()
    except DatabaseError:
        raise HTTPException(500, "Unable to update player data")

    return RedirectResponse(f"/history/{game_id}", status_code=303)
