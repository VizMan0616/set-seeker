"""htmx search endpoints (phase0-contracts §5).

Form bodies are parsed as plain urlencoded data (what htmx posts by default)
with urllib.parse — python-multipart is deliberately not a dependency
(phase0-contracts §2), and Starlette's request.form() would require it.
"""

from collections.abc import Callable
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.domain.models import (
    CHARM_MODES,
    DEFAULT_CHARM_MODE,
    Query,
    SkillRequest,
    charm_mode_uses_generated,
)
from app.engine.data import PackData
from app.engine.pruning import apply_rel_checks, prune
from app.repository.game_data import GameDataRepository
from app.web.present import advanced_columns, page_context
from app.web.render import templates
from app.web.resolvers import desired_skills_max, progression_caps

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


def _charm_mode(fields: FormFields) -> str:
    raw = _first(fields, "charm_mode", DEFAULT_CHARM_MODE)
    if raw in CHARM_MODES:
        return raw
    if _first(fields, "use_generated_charms", "on") != "on":
        return "inventory"
    return DEFAULT_CHARM_MODE


def _optional_int(fields: FormFields, key: str) -> int | None:
    value = _first(fields, key).strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {key}.") from exc


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


def _parse_query(
    game: str,
    fields: FormFields,
    repo: GameDataRepository,
    pack_loader: Callable[[str], PackData] | None = None,
) -> Query:
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

    skill_cap = desired_skills_max(game_row["features"])
    if not 1 <= len(skills) <= skill_cap:
        raise HTTPException(
            status_code=422,
            detail=f"Choose between 1 and {skill_cap} skills.",
        )

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

    caps = progression_caps(game_row["features"])
    hr = _optional_int(fields, "hr")
    village = _optional_int(fields, "village_stars")
    # Clamp leftover ranks from a previous game (MHFU 9 vs MHP3 6). Do not 422
    # — htmx only swaps 2xx, so a 422 looks like “no results at all”.
    if hr is not None:
        if hr < 1:
            hr = None
        elif hr > caps["guild_rank"]:
            hr = caps["guild_rank"]
    if village is not None:
        if village < 1:
            village = None
        elif village > caps["village_stars"]:
            village = caps["village_stars"]

    mode = _charm_mode(fields)
    query = Query(
        game=game,
        skills=tuple(skills),
        weapon_slots=weapon_slots,
        gender=gender,
        hunter_type=hunter_type,
        hr=hr,
        village_stars=village,
        allow_event=_first(fields, "allow_event") == "on",
        allow_bad_skills=_first(fields, "allow_bad_skills") == "on",
        allow_torso_inc=_first(fields, "allow_torso_inc") == "on",
        allow_dummy=_first(fields, "allow_dummy") == "on",
        excluded_piece_ids=_int_ids(fields, "excluded_piece_id"),
        excluded_decoration_ids=_int_ids(fields, "excluded_decoration_id"),
        excluded_charm_ids=_int_ids(fields, "excluded_charm_id"),
        forced_piece_ids=_int_ids(fields, "forced_piece_id"),
        forced_decoration_ids=_int_ids(fields, "forced_decoration_id"),
        forced_charm_ids=_int_ids(fields, "forced_charm_id"),
        sort=_first(fields, "sort", "defense"),
        expand_equivalents=_first(fields, "expand_equivalents") == "on",
        charm_mode=mode,
        use_generated_charms=charm_mode_uses_generated(mode),
    )
    if pack_loader is not None and _first(fields, "advanced_domain") == "1":
        query = apply_rel_checks(
            query,
            pack_loader(game),
            _int_ids(fields, "rel_piece_id"),
            _int_ids(fields, "rel_decoration_id"),
            _int_ids(fields, "rel_charm_id"),
        )
    return query


def _search_page_context(request: Request, game: str, query: Query, page) -> dict:
    pack = request.app.state.pack_loader(game)
    stored = request.app.state.search_service.get_search_query(
        request.state.session_id, page.search_id
    )
    query = stored or query
    pruned = prune(pack, query)
    return page_context(
        page,
        request.app.state.name_resolver,
        advanced=advanced_columns(pack, pruned, query, request.app.state.name_resolver),
        expand_equivalents=query.expand_equivalents,
    )


@router.post("/search", response_class=HTMLResponse)
async def start_search_from_picker(request: Request) -> HTMLResponse:
    fields = await _read_form(request)
    game = _first(fields, "game")
    if not game:
        return templates.TemplateResponse(
            request, "search/error.html", {"message": "Unknown game."},
        )
    return _start_search(request, game, fields)


@router.post("/games/{game}/search", response_class=HTMLResponse)
async def start_search(request: Request, game: str) -> HTMLResponse:
    fields = await _read_form(request)
    picked = _first(fields, "game")
    if picked:
        game = picked
    return _start_search(request, game, fields)


def _start_search(request: Request, game: str, fields: FormFields) -> HTMLResponse:
    try:
        query = _parse_query(
            game,
            fields,
            request.app.state.game_data,
            request.app.state.pack_loader,
        )
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "search/error.html",
            {"message": exc.detail},
        )
    page = request.app.state.search_service.start_search(request.state.session_id, query)
    return templates.TemplateResponse(
        request, "search/results.html", _search_page_context(request, game, query, page)
    )


@router.post("/search/{search_id}/more", response_class=HTMLResponse)
async def load_more(request: Request, search_id: str) -> HTMLResponse:
    page = request.app.state.search_service.load_more(request.state.session_id, search_id)
    query = request.app.state.search_service.get_search_query(
        request.state.session_id, search_id
    )
    context = page_context(
        page,
        request.app.state.name_resolver,
        expand_equivalents=bool(query and query.expand_equivalents),
    )
    return templates.TemplateResponse(request, "search/more.html", context)


@router.get("/search/{search_id}/advanced", response_class=HTMLResponse)
async def advanced_domain(request: Request, search_id: str) -> HTMLResponse:
    service = request.app.state.search_service
    query = service.get_search_query(request.state.session_id, search_id)
    if query is None:
        raise HTTPException(status_code=404, detail="Unknown search.")
    pack = request.app.state.pack_loader(query.game)
    pruned = prune(pack, query)
    return templates.TemplateResponse(
        request,
        "search/_advanced_modal_body.html",
        {
            "advanced_columns": advanced_columns(
                pack, pruned, query, request.app.state.name_resolver
            )
        },
    )
