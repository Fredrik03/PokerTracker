from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from deps import get_current_user
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/history", response_class=HTMLResponse)
def history(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)

    with get_db() as db:
        games = db.execute(
            """
            SELECT date, winner, amount
              FROM games
          ORDER BY date DESC
            """
        ).fetchall()

    return templates.TemplateResponse(
        "history.html",
        {"request": request, "games": games}
    )
