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
    default_game = games[0]["code"] if games else "mhfu"
    catalogs = {g["code"]: catalog.list_search_catalog(g["code"]) for g in games}
    default_catalog = catalogs.get(default_game, {
        "categories": [], "skills": [],
        "pieces": {s: [] for s in ("head", "body", "arms", "waist", "legs")},
        "decorations": [],
    })
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "games": games,
            "skill_trees": catalog.list_skill_trees(default_game) if games else [],
            "skills": default_catalog["skills"],
            "categories": default_catalog["categories"],
            "pieces": default_catalog["pieces"],
            "decorations": default_catalog["decorations"],
            "catalogs": catalogs,
            "max_skill_picks": MAX_SKILL_PICKS,
        },
    )
