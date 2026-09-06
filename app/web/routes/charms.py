"""Charm inventory fragments (ADR 0006). Shown only when pack flag talismans is true."""

from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.web.render import templates
from app.web.resolvers import charm_point_bounds, torso_inc_display_name

router = APIRouter()


def _features(game_row: dict) -> dict:
    import json

    return json.loads(game_row.get("features") or "{}")


def _require_talisman_game(request: Request, game: str) -> dict:
    repo = request.app.state.game_data
    row = repo.get_game_by_code(game)
    if row is None or not _features(row).get("talismans"):
        raise HTTPException(status_code=404, detail="This game has no talismans.")
    return row


def _tree_options(request: Request, game: str) -> list[dict]:
    row = request.app.state.game_data.get_game_by_code(game)
    skip = (
        torso_inc_display_name(request.app.state.game_data, row["id"], row.get("features"))
        if row is not None
        else None
    )
    return [
        tree for tree in request.app.state.catalog.list_skill_trees(game) if tree["name"] != skip
    ]


def _labeled_charms(request: Request, session_id: str, game_id: int) -> list[dict]:
    resolver = request.app.state.name_resolver
    rows = request.app.state.user_data.list_charms(session_id, game_id)
    labeled = []
    for row in rows:
        parts = []
        if row.get("skill1_tree") is not None:
            parts.append(
                f"{resolver.skill_tree_name(row['skill1_tree'])} {row['skill1_points']:+d}"
            )
        if row.get("skill2_tree") is not None:
            parts.append(
                f"{resolver.skill_tree_name(row['skill2_tree'])} {row['skill2_points']:+d}"
            )
        pips = "O" * row["slots"] + "-" * (3 - row["slots"])
        labeled.append({**row, "label": (", ".join(parts) + f" {pips}").strip()})
    return labeled


def _charm_fragment(request: Request, row: dict) -> HTMLResponse:
    user_data = request.app.state.user_data
    user_data.get_or_create_session(request.state.session_id)
    bounds = charm_point_bounds(row.get("features"))
    return templates.TemplateResponse(
        request,
        "charms.html",
        {
            "game": row,
            "trees": _tree_options(request, row["code"]),
            "charms": _labeled_charms(request, request.state.session_id, row["id"]),
            "charm_points": bounds,
        },
    )


@router.get("/games/{game}/charms", response_class=HTMLResponse)
def list_charms(request: Request, game: str) -> HTMLResponse:
    row = _require_talisman_game(request, game)
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url="/", status_code=303)
    return _charm_fragment(request, row)


@router.post("/games/{game}/charms", response_class=HTMLResponse)
async def add_charm(request: Request, game: str) -> HTMLResponse:
    row = _require_talisman_game(request, game)
    raw = (await request.body()).decode("utf-8")
    fields: dict[str, list[str]] = {}
    for key, value in parse_qsl(raw, keep_blank_values=True):
        fields.setdefault(key, []).append(value)

    def first(key: str, default: str = "") -> str:
        values = fields.get(key)
        return values[0] if values else default

    try:
        slots = int(first("slots", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid slots.") from exc
    if slots not in (0, 1, 2, 3):
        raise HTTPException(status_code=422, detail="Slots must be 0–3.")

    trees = {t["id"] for t in _tree_options(request, game)}
    bounds = charm_point_bounds(row.get("features"))

    def skill_pair(prefix: str) -> tuple[int | None, int | None]:
        raw_tree = first(f"{prefix}_tree").strip()
        raw_pts = first(f"{prefix}_points").strip()
        if not raw_tree:
            return None, None
        try:
            tree_id = int(raw_tree)
            points = int(raw_pts or "0")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid charm skill.") from exc
        if tree_id not in trees:
            raise HTTPException(status_code=422, detail="Skill tree is not in this game.")
        lo = bounds[f"{prefix}_min"]
        hi = bounds[f"{prefix}_max"]
        if points == 0 or not lo <= points <= hi:
            raise HTTPException(status_code=422, detail="Charm points must be nonzero.")
        return tree_id, points

    s1_tree, s1_pts = skill_pair("skill1")
    s2_tree, s2_pts = skill_pair("skill2")
    if s2_tree is not None and s1_tree is None:
        raise HTTPException(status_code=422, detail="Set the first skill before the second.")
    if s1_tree is not None and s2_tree == s1_tree:
        raise HTTPException(status_code=422, detail="Charm skills must be different trees.")
    if s1_tree is None and slots == 0:
        raise HTTPException(status_code=422, detail="Add a skill or at least one slot.")

    user_data = request.app.state.user_data
    user_data.get_or_create_session(request.state.session_id)
    user_data.add_charm(
        session_id=request.state.session_id,
        game_id=row["id"],
        slots=slots,
        skill1_tree=s1_tree,
        skill1_points=s1_pts,
        skill2_tree=s2_tree,
        skill2_points=s2_pts,
        note=(first("note").strip() or None),
    )
    return _charm_fragment(request, row)


@router.post("/games/{game}/charms/{charm_id}/delete", response_class=HTMLResponse)
def delete_charm(request: Request, game: str, charm_id: int) -> HTMLResponse:
    row = _require_talisman_game(request, game)
    user_data = request.app.state.user_data
    existing = user_data.get_charm(charm_id)
    if (
        existing is None
        or existing["session_id"] != request.state.session_id
        or existing["game_id"] != row["id"]
    ):
        raise HTTPException(status_code=404, detail="Unknown talisman.")
    user_data.delete_charm(charm_id)
    return _charm_fragment(request, row)
