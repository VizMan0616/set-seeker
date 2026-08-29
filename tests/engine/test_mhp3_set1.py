"""Replay Set1.txt (local MHP3 mix) against the real pack + CP-SAT.

Athena lists eight Weakness Exploit + Evasion +2 sets that use
``Volvidon Greaves (or anything with Torso Up)``. Encoded here so the
gitignored mix file is not required.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.domain.models import Query, SkillRequest
from app.engine.data import LEGS
from app.engine.pruning import prune
from app.engine.solver import solve_one
from app.etl.loaders import load_pack
from app.etl.manifest import load_manifest
from app.etl.writer import PackWriter
from app.pack_loader import PackLoader
from app.repository import tables
from app.repository.game_data import GameDataRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "packs" / "mhp3"
SOLVE_MS = 8000

# Set1.txt cores: legs are any Torso Up piece (Athena "or anything with Torso Up").
SET1_CORES = (
    ("Volvidon Cap", "Lagombi Mail", "Rathalos Vambraces", "Volvidon Faulds"),
    ("Volvidon Cap", "Rathalos Mail", "Volvidon Vambraces", "Volvidon Faulds"),
    ("Volvidon Cap", "Rathalos Mail", "Rathalos Vambraces", "Volvidon Faulds"),
    ("Volvidon Cap", "Rathalos Mail", "Mosgharl Creeper S", "Volvidon Faulds"),
    ("Mosgharl Brim S", "Lagombi Mail", "Rathalos Vambraces", "Volvidon Faulds"),
    ("Mosgharl Brim S", "Rathalos Mail", "Volvidon Vambraces", "Volvidon Faulds"),
    ("Mosgharl Brim S", "Rathalos Mail", "Rathalos Vambraces", "Volvidon Faulds"),
    ("Mosgharl Brim S", "Rathalos Mail", "Mosgharl Creeper S", "Volvidon Faulds"),
)


@pytest.fixture(scope="module")
def mhp3_pack(tmp_path_factory):
    manifest = load_manifest(PACK_DIR)
    pack_data = load_pack(manifest)
    db_path = tmp_path_factory.mktemp("mhp3_set1") / "mhp3.db"
    engine = create_engine(f"sqlite:///{db_path}")
    tables.metadata.create_all(engine)
    repo = GameDataRepository(engine)
    PackWriter(repo).rebuild_pack(manifest, pack_data)
    game_id = repo.get_game_by_code("mhp3")["id"]
    pack = PackLoader(repo)("mhp3")
    pieces = {
        (p["slot"], p["name_en"]): p
        for p in repo.list_armor_pieces(game_id, allow_event=True)
    }
    skills = {s["name_en"]: s for s in repo.list_skills_for_game(game_id)}
    return {
        "repo": repo,
        "game_id": game_id,
        "pack": pack,
        "pieces": pieces,
        "skills": skills,
        "by_id": {p.id: p for p in pack.pieces},
    }


def _set1_query(ctx, *, allow_torso_inc: bool) -> Query:
    exploit = ctx["skills"]["Weakness Exploit"]
    evasion = ctx["skills"]["Evasion +2"]
    return Query(
        game="mhp3",
        skills=(
            SkillRequest(tree_id=exploit["tree_id"], min_points=exploit["points"]),
            SkillRequest(tree_id=evasion["tree_id"], min_points=evasion["points"]),
        ),
        weapon_slots=1,
        gender="f",
        hunter_type="blademaster",
        hr=2,
        village_stars=6,
        allow_torso_inc=allow_torso_inc,
        charm_mode="one_skill",
    )


def test_volvidon_greaves_are_torso_up(mhp3_pack):
    greaves = mhp3_pack["pieces"][(LEGS, "Volvidon Greaves")]
    assert greaves["torso_inc"] is True or greaves["torso_inc"] == 1
    features = mhp3_pack["repo"].get_game(mhp3_pack["game_id"])["features"]
    import json
    assert json.loads(features)["torso_inc_name"] == "Torso Up"


def test_set1_query_keeps_torso_up_legs_when_allowed(mhp3_pack):
    query = _set1_query(mhp3_pack, allow_torso_inc=True)
    pruned = prune(mhp3_pack["pack"], query)
    greaves_id = mhp3_pack["pieces"][(LEGS, "Volvidon Greaves")]["id"]
    legs = {m.id for c in pruned.classes[LEGS] for m in c.members}
    assert greaves_id in legs

    off = prune(mhp3_pack["pack"], _set1_query(mhp3_pack, allow_torso_inc=False))
    off_legs = {m.id for c in off.classes[LEGS] for m in c.members}
    assert greaves_id not in off_legs
    assert not any(
        m.torso_inc
        for slot in off.classes
        for c in slot
        for m in c.members
    )


def test_set1_search_finds_torso_up_sets(mhp3_pack):
    query = _set1_query(mhp3_pack, allow_torso_inc=True)
    pack = mhp3_pack["pack"]
    pruned = prune(pack, query)
    names = {row["id"]: name for (_slot, name), row in mhp3_pack["pieces"].items()}
    found_cores: set[tuple[str, str, str, str]] = set()
    used_torso = False
    exclusions: list[tuple[int, ...]] = []
    for _ in range(24):
        outcome = solve_one(
            pack=pack, pruned=pruned, query=query,
            exclusions=exclusions, time_limit_ms=SOLVE_MS,
        )
        if outcome.result is None:
            break
        result = outcome.result
        exclusions.append(result.piece_ids + ((result.charm_id or 0),))
        pieces = [mhp3_pack["by_id"][pid] for pid in result.piece_ids]
        if any(p.torso_inc for p in pieces):
            used_torso = True
        core = tuple(names[pid] for pid in result.piece_ids[:4])
        if core in SET1_CORES and pieces[LEGS].torso_inc:
            found_cores.add(core)

    assert used_torso, "Set1 query must return at least one Torso Up set"
    assert found_cores, (
        "expected a Set1.txt core (head/body/arms/waist) with Torso Up legs; "
        "none in the first 24 solutions"
    )


def test_set1_search_without_torso_up_omits_flagged_pieces(mhp3_pack):
    query = _set1_query(mhp3_pack, allow_torso_inc=False)
    pack = mhp3_pack["pack"]
    pruned = prune(pack, query)
    exclusions: list[tuple[int, ...]] = []
    for _ in range(8):
        outcome = solve_one(
            pack=pack, pruned=pruned, query=query,
            exclusions=exclusions, time_limit_ms=SOLVE_MS,
        )
        if outcome.result is None:
            break
        result = outcome.result
        exclusions.append(result.piece_ids + ((result.charm_id or 0),))
        for pid in result.piece_ids:
            assert not mhp3_pack["by_id"][pid].torso_inc
