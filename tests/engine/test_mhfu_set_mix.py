"""Replay community MHFU set-mix builds against the real pack + CP-SAT.

See tests/fixtures/mhfu_set_mix_RULES.md. Pass A is a direct feasibility
check of the recorded pieces/jewels/skills. Pass B asks the engine for
any set that activates those skills.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.models import Query, SkillRequest
from app.engine.data import BODY
from app.engine.pruning import prune
from app.engine.solver import solve_one
from app.pack_loader import PackLoader

pytest_plugins = ["tests.etl.conftest"]

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mhfu_set_mix.json"
SLOTS = ("head", "body", "arms", "waist", "legs")
PASS_B_DEFAULT_CAP = 12
SOLVE_MS = 4000

_DOC = json.loads(FIXTURE.read_text())
_RECORDS = _DOC["records"]
_BY_ID = {r["id"]: r for r in _RECORDS}


def _fully_mapped() -> list[dict]:
    return [r for r in _RECORDS if r["fully_mapped"]]


def _hardness(record: dict) -> tuple[int, int]:
    jewels = sum(j["count"] for j in record["jewels"])
    return (len(record["skills"]), jewels)


def _hardest(n: int) -> list[dict]:
    return sorted(_fully_mapped(), key=_hardness, reverse=True)[:n]


def _positive_skills(record: dict) -> list[dict]:
    return [
        s for s in record["skills"]
        if s["mapped"] and s["min_points"] is not None and s["min_points"] > 0
    ]


@pytest.fixture(scope="module")
def mhfu_pack(etl_db):
    repo, game_id, _ = etl_db
    pack = PackLoader(repo)("mhfu")
    pieces_by_slot_name: dict[tuple[int, str], list] = {}
    for p in repo.list_armor_pieces(game_id, allow_event=True):
        pieces_by_slot_name.setdefault((p["slot"], p["name_en"]), []).append(p)
    decos = {d["name_en"]: d for d in repo.list_decorations(game_id, allow_event=True)}
    trees = {t["name_en"]: t for t in repo.list_skill_trees(game_id)}
    pack_piece = {p.id: p for p in pack.pieces}
    pack_deco = {d.id: d for d in pack.decorations}
    return {
        "repo": repo,
        "game_id": game_id,
        "pack": pack,
        "pieces_by_slot_name": pieces_by_slot_name,
        "decos": decos,
        "trees": trees,
        "pack_piece": pack_piece,
        "pack_deco": pack_deco,
    }


def _resolve_pieces(record: dict, ctx: dict) -> list[dict] | str:
    rows = []
    for slot, key in enumerate(SLOTS):
        entry = record["pieces"][key]
        if not entry.get("mapped") or not entry.get("name_en"):
            return f"unmapped piece {key}: {entry.get('source_name')!r}"
        names = [entry["name_en"], *entry.get("alternates_name_en", [])]
        found = None
        for name in names:
            hits = ctx["pieces_by_slot_name"].get((slot, name))
            if hits:
                found = hits[0]
                break
        if found is None:
            return f"pack missing {key} {entry['name_en']!r}"
        rows.append(found)
    return rows


def _infer_gender(piece_rows: list[dict]) -> str:
    gendered = {p["gender"] for p in piece_rows if p["gender"] in (0, 1)}
    if gendered == {1}:
        return "f"
    return "m"


def _combo_points_and_slots(record: dict, piece_rows: list[dict], ctx: dict):
    pack_piece = ctx["pack_piece"]
    pack_deco = ctx["pack_deco"]
    points: dict[int, int] = {}
    engine_pieces = [pack_piece[r["id"]] for r in piece_rows]
    torso = engine_pieces[BODY].torso_inc

    def add(tree_id: int, pts: int, *, doubled: bool) -> None:
        points[tree_id] = points.get(tree_id, 0) + pts * (2 if doubled else 1)

    for ep in engine_pieces:
        for tree_id, pts in ep.skills:
            add(tree_id, pts, doubled=torso and ep.slot == BODY)

    def place(jewel_entries: list[dict], capacity: int, *, body: bool) -> str | None:
        used = 0
        for j in jewel_entries:
            if not j["mapped"]:
                return f"unmapped jewel {j['source_name']!r}"
            drow = ctx["decos"].get(j["name_en"])
            if drow is None:
                return f"pack missing jewel {j['name_en']!r}"
            deco = pack_deco[drow["id"]]
            used += deco.size * j["count"]
            for tree_id, pts in deco.skills:
                add(tree_id, pts * j["count"], doubled=torso and body)
        if used > capacity:
            return f"jewels need {used} sockets, capacity {capacity}"
        return None

    for slot, key in enumerate(SLOTS):
        err = place(record["pieces"][key]["jewels"], engine_pieces[slot].slots,
                    body=slot == BODY)
        if err:
            return None, err
    err = place(record["weapon_jewels"], record["weapon_slots"] or 0, body=False)
    if err:
        return None, err
    return points, None


def _skip_if_incomplete(record: dict) -> None:
    if record["fully_mapped"]:
        return
    bits = list(record.get("skip_reasons") or ["incomplete"])
    for slot in SLOTS:
        p = record["pieces"][slot]
        if not p.get("mapped"):
            bits.append(f"{slot}={p.get('source_name')!r}")
    pytest.skip(", ".join(bits))


def _pass_a(record: dict, ctx: dict) -> str | None:
    """Return None if the recorded combo is feasible, else an error string."""
    pieces = _resolve_pieces(record, ctx)
    if isinstance(pieces, str):
        return pieces
    points, err = _combo_points_and_slots(record, pieces, ctx)
    if err:
        return err
    trees = ctx["trees"]
    missing = []
    for skill in _positive_skills(record):
        tree = trees.get(skill["tree_name"])
        if tree is None:
            missing.append(f"no tree {skill['tree_name']!r}")
            continue
        got = points.get(tree["id"], 0)
        if got < skill["min_points"]:
            missing.append(
                f"{skill['skill_name_en']} needs {skill['min_points']} "
                f"on {skill['tree_name']}, got {got}"
            )
    if missing:
        return "; ".join(missing)
    return None


@pytest.mark.parametrize("record_id", [r["id"] for r in _RECORDS])
def test_pass_a_recorded_combo_is_feasible(record_id: str, mhfu_pack):
    """Fully-mapped rows must be socket- and point-legal against the pack."""
    record = _BY_ID[record_id]
    _skip_if_incomplete(record)
    err = _pass_a(record, mhfu_pack)
    assert err is None, f"{record['title']}: {err}"


def _pass_b(record: dict, mhfu_pack, gender: str):
    trees = mhfu_pack["trees"]
    reqs = []
    for skill in _positive_skills(record)[:5]:
        tree = trees[skill["tree_name"]]
        reqs.append(SkillRequest(tree_id=tree["id"], min_points=skill["min_points"]))
    if not reqs:
        pytest.skip("no positive skills")
    query = Query(
        game="mhfu",
        skills=tuple(reqs),
        weapon_slots=record["weapon_slots"] or 0,
        gender=gender,
        hunter_type=record["hunter_type"] if record["hunter_type"] in (
            "blademaster", "gunner"
        ) else "blademaster",
        hr=None,
        village_stars=None,
        allow_event=True,
        allow_bad_skills=True,
    )
    pack = mhfu_pack["pack"]
    outcome = solve_one(
        pack=pack,
        pruned=prune(pack, query),
        query=query,
        exclusions=[],
        time_limit_ms=SOLVE_MS,
        num_workers=8,
    )
    return query, outcome


def _run_pass_b(record: dict, mhfu_pack):
    pieces = _resolve_pieces(record, mhfu_pack)
    gender = _infer_gender(pieces) if not isinstance(pieces, str) else "m"
    query, outcome = _pass_b(record, mhfu_pack, gender)
    if outcome.result is None and gender == "m":
        query, outcome = _pass_b(record, mhfu_pack, "f")
    assert outcome.status in {"optimal", "feasible"}, (
        f"{record['title']}: engine {outcome.status} for "
        f"{[(s.tree_id, s.min_points) for s in query.skills]} "
        f"ws={query.weapon_slots} {query.hunter_type}/{query.gender}"
    )
    assert outcome.result is not None
    tree_of = {sk.id: sk.tree_id for sk in mhfu_pack["pack"].skills}
    achieved = {}
    for skill_id, pts in outcome.result.active_skills:
        tree_id = tree_of[skill_id]
        achieved[tree_id] = max(achieved.get(tree_id, 0), pts)
    for sr in query.skills:
        assert achieved.get(sr.tree_id, 0) >= sr.min_points, (
            f"{record['title']}: tree {sr.tree_id} got "
            f"{achieved.get(sr.tree_id)} want {sr.min_points}"
        )


@pytest.mark.parametrize("record_id", [r["id"] for r in _hardest(PASS_B_DEFAULT_CAP)])
def test_pass_b_engine_finds_a_set_default_subset(record_id: str, mhfu_pack):
    record = _BY_ID[record_id]
    _skip_if_incomplete(record)
    _run_pass_b(record, mhfu_pack)


@pytest.mark.mhfu_set_mix_full
@pytest.mark.parametrize("record_id", [r["id"] for r in _fully_mapped()])
def test_pass_b_engine_finds_a_set_full(record_id: str, mhfu_pack):
    record = _BY_ID[record_id]
    _run_pass_b(record, mhfu_pack)


def test_fixture_meta_lists_unmapped_and_dump_illegal():
    unmapped = _DOC["meta"]["mapping"]["unmapped_armor"]
    assert "Kirin Hoop Z" in unmapped
    assert "Guardian Spirit Raiment X" in unmapped
    assert _DOC["meta"]["counts"]["raw"] == len(_RECORDS)
    skipped = [r for r in _RECORDS if not r["fully_mapped"]]
    assert len(skipped) == _DOC["meta"]["counts"]["skipped"]
    dump_ids = {d["id"] for d in _DOC["meta"]["mapping"]["dump_illegal"]}
    assert dump_ids <= {r["id"] for r in skipped}
