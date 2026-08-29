"""GET pages (phase0-contracts §5)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.web.render import templates
from app.web.resolvers import DEFAULT_DESIRED_SKILLS_MAX

router = APIRouter()


@router.get("/health", response_class=PlainTextResponse)
def health() -> str:
    """Cheap liveness probe — must stay off the solver slot."""
    return "ok"


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    catalog = request.app.state.catalog
    games = catalog.list_games()
    default_game = games[0]["code"] if games else "mhfu"
    catalogs = {g["code"]: catalog.list_search_catalog(g["code"]) for g in games}
    default_catalog = catalogs.get(default_game, {
        "categories": [], "skills": [],
        "progression": {"guild_rank": 9, "village_stars": 9},
        "talismans": False,
        "has_dummy": False,
        "desired_skills_max": DEFAULT_DESIRED_SKILLS_MAX,
    })
    max_skill_picks = max(
        (int(c.get("desired_skills_max") or DEFAULT_DESIRED_SKILLS_MAX) for c in catalogs.values()),
        default=DEFAULT_DESIRED_SKILLS_MAX,
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "games": games,
            "skill_trees": catalog.list_skill_trees(default_game) if games else [],
            "skills": default_catalog["skills"],
            "categories": default_catalog["categories"],
            "catalogs": catalogs,
            "max_skill_picks": max_skill_picks,
            "progression": default_catalog.get(
                "progression", {"guild_rank": 9, "village_stars": 9}
            ),
        },
    )
