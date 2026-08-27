"""htmx search endpoints (phase0-contracts §5).

Form bodies are parsed as plain urlencoded data (what htmx posts by default)
with urllib.parse — python-multipart is deliberately not a dependency
(phase0-contracts §2), and Starlette's request.form() would require it.
"""

from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.domain.models import Query, SkillRequest
from app.repository.game_data import GameDataRepository
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


def _int_ids(fields: FormFields, key: str) -> tuple[int, ...]:
    seen: list[int] = []
    for raw in fields.get(key, []):
        value = raw.strip()
        if not value:
            continue
        try:
            ident = int(value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid {key}.") from exc
        if ident not in seen:
            seen.append(ident)
    return tuple(sorted(seen))


def _parse_query(game: str, fields: FormFields, repo: GameDataRepository) -> Query:
    game_row = repo.get_game_by_code(game)
    if game_row is None:
        raise HTTPException(status_code=422, detail="Unknown game.")

    skills: list[SkillRequest] = []
    seen_trees: set[int] = set()
    for raw in fields.get("skill_id", []):
        value = raw.strip()
        if not value:
            continue
        try:
            skill_id = int(value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid skill.") from exc
        skill = repo.get_skill(skill_id)
        if skill is None:
            raise HTTPException(status_code=422, detail="Unknown skill.")
        tree = repo.get_skill_tree(skill["tree_id"])
        if tree is None or tree["game_id"] != game_row["id"]:
            raise HTTPException(status_code=422, detail="Skill is not in this game.")
        if skill["is_negative"] or skill["points"] <= 0:
            raise HTTPException(
                status_code=422,
                detail="Choose an activated skill, not a penalty.",
            )
        if skill["tree_id"] in seen_trees:
            raise HTTPException(status_code=422, detail="Duplicate skill tree.")
        seen_trees.add(skill["tree_id"])
        # Threshold comes from the skills table — never from the client.
        skills.append(SkillRequest(tree_id=skill["tree_id"], min_points=skill["points"]))

    if not 1 <= len(skills) <= 5:
        raise HTTPException(status_code=422, detail="Choose between 1 and 5 skills.")

    try:
        weapon_slots = int(_first(fields, "weapon_slots", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid weapon slots.") from exc
    if weapon_slots not in (0, 1, 2, 3):
        raise HTTPException(status_code=422, detail="Invalid weapon slots.")

    gender = _first(fields, "gender", "m")
    hunter_type = _first(fields, "hunter_type", "blademaster")
    if gender not in ("m", "f") or hunter_type not in ("blademaster", "gunner"):
        raise HTTPException(status_code=422, detail="Invalid hunter filters.")

    return Query(
        game=game,
        skills=tuple(skills),
        weapon_slots=weapon_slots,
        gender=gender,
        hunter_type=hunter_type,
        hr=_optional_int(fields, "hr"),
        village_stars=_optional_int(fields, "village_stars"),
        allow_event=_first(fields, "allow_event") == "on",
        allow_bad_skills=_first(fields, "allow_bad_skills") == "on",
        allow_torso_inc=_first(fields, "allow_torso_inc") == "on",
        allow_dummy=_first(fields, "allow_dummy") == "on",
        excluded_piece_ids=_int_ids(fields, "excluded_piece_id"),
        excluded_decoration_ids=_int_ids(fields, "excluded_decoration_id"),
        sort=_first(fields, "sort", "defense"),
    )


@router.post("/games/{game}/search", response_class=HTMLResponse)
async def start_search(request: Request, game: str) -> HTMLResponse:
    query = _parse_query(game, await _read_form(request), request.app.state.game_data)
    page = request.app.state.search_service.start_search(request.state.session_id, query)
    context = page_context(page, request.app.state.name_resolver)
    return templates.TemplateResponse(request, "search/results.html", context)


@router.post("/search/{search_id}/more", response_class=HTMLResponse)
async def load_more(request: Request, search_id: str) -> HTMLResponse:
    page = request.app.state.search_service.load_more(request.state.session_id, search_id)
    context = page_context(page, request.app.state.name_resolver)
    return templates.TemplateResponse(request, "search/more.html", context)
