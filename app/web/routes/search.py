"""htmx search endpoints (phase0-contracts §5).

Form bodies are parsed as plain urlencoded data (what htmx posts by default)
with urllib.parse — python-multipart is deliberately not a dependency
(phase0-contracts §2), and Starlette's request.form() would require it.
"""

from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.domain.models import Query, SkillRequest
from app.web.present import page_context
from app.web.render import templates

router = APIRouter()

FormFields = dict[str, list[str]]


async def _read_form(request: Request) -> FormFields:
    raw = (await request.body()).decode("utf-8")
    fields: FormFields = {}
    for key, value in parse_qsl(raw, keep_blank_values=True):
        fields.setdefault(key, []).append(value)
    return fields


def _first(fields: FormFields, key: str, default: str = "") -> str:
    values = fields.get(key)
    return values[0] if values else default


def _optional_int(fields: FormFields, key: str) -> int | None:
    value = _first(fields, key).strip()
    return int(value) if value else None


def _parse_query(game: str, fields: FormFields) -> Query:
    skills = []
    for tree, points in zip(
        fields.get("skill_tree", []), fields.get("skill_points", []), strict=False
    ):
        if tree.strip() and points.strip():
            skills.append(SkillRequest(tree_id=int(tree), min_points=int(points)))
    if not 1 <= len(skills) <= 5:
        raise HTTPException(status_code=422, detail="Choose between 1 and 5 skills.")
    return Query(
        game=game,
        skills=tuple(skills),
        weapon_slots=int(_first(fields, "weapon_slots", "0")),
        gender=_first(fields, "gender", "m"),
        hunter_type=_first(fields, "hunter_type", "blademaster"),
        hr=_optional_int(fields, "hr"),
        village_stars=_optional_int(fields, "village_stars"),
        allow_event=_first(fields, "allow_event") == "on",
        allow_bad_skills=_first(fields, "allow_bad_skills") == "on",
        sort=_first(fields, "sort", "defense"),
    )


@router.post("/games/{game}/search", response_class=HTMLResponse)
async def start_search(request: Request, game: str) -> HTMLResponse:
    query = _parse_query(game, await _read_form(request))
    page = request.app.state.search_service.start_search(request.state.session_id, query)
    context = page_context(page, request.app.state.name_resolver)
    return templates.TemplateResponse(request, "search/results.html", context)


@router.post("/search/{search_id}/more", response_class=HTMLResponse)
async def load_more(request: Request, search_id: str) -> HTMLResponse:
    page = request.app.state.search_service.load_more(request.state.session_id, search_id)
    context = page_context(page, request.app.state.name_resolver)
    return templates.TemplateResponse(request, "search/more.html", context)
