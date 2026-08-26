"""GET pages (phase0-contracts §5)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.web.render import templates

router = APIRouter()

MAX_SKILL_PICKS = 5


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    catalog = request.app.state.catalog
    games = catalog.list_games()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "games": games,
            "skill_trees": catalog.list_skill_trees(games[0]["code"]) if games else [],
            "max_skill_picks": MAX_SKILL_PICKS,
        },
    )
