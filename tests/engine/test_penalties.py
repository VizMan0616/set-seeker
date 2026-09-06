"""Penalty neutralization: fixer jewels in prune + solver (ADR 0011).

Uses a dummy negative tree — not Health/Vitality or any pack-specific name.
"""

from dataclasses import replace

from app.engine.data import HEAD, Decoration, PackData, SkillThreshold
from app.engine.pruning import prune
from app.engine.solver import solve_one
from tests.engine.conftest import make_query

GLOOM_TREE = 7
ORPHAN_TREE = 8
GLOOM_DOWN_ID = 50
FIXER_DECO_ID = 201
ORPHAN_DECO_ID = 202
HARMFUL_FIXER_DECO_ID = 203


def _gloom_pack(tiny: PackData, *, with_fixer: bool = True) -> PackData:
    pieces = tuple(
        replace(p, skills=p.skills + ((GLOOM_TREE, -10),)) if p.slot == HEAD else p
        for p in tiny.pieces
    )
    extra_decos = []
    if with_fixer:
        extra_decos.append(Decoration(id=FIXER_DECO_ID, size=1, skills=((GLOOM_TREE, 1),)))
        extra_decos.append(Decoration(id=HARMFUL_FIXER_DECO_ID, size=1, skills=((GLOOM_TREE, -1),)))
    extra_decos.append(Decoration(id=ORPHAN_DECO_ID, size=1, skills=((ORPHAN_TREE, 1),)))
    return PackData(
        game=tiny.game,
        game_id=tiny.game_id,
        pieces=pieces,
        decorations=tiny.decorations + tuple(extra_decos),
        skills=tiny.skills
        + (
            SkillThreshold(id=GLOOM_DOWN_ID, tree_id=GLOOM_TREE, points=-10, is_negative=True),
            SkillThreshold(id=51, tree_id=ORPHAN_TREE, points=-10, is_negative=True),
        ),
        talismans=tiny.talismans,
    )


def test_fixer_jewel_enters_domain_only_for_present_penalty_trees(tiny_pack_data):
    pack = _gloom_pack(tiny_pack_data)
    pruned = prune(pack, make_query(min_points=10))
    deco_ids = {d.id for d in pruned.decorations}
    assert FIXER_DECO_ID in deco_ids
    assert ORPHAN_DECO_ID not in deco_ids
    assert pruned.bad_tree_thresholds == ((GLOOM_TREE, -10), (ORPHAN_TREE, -10))


def test_harmful_fixer_jewel_is_pruned_from_domain(tiny_pack_data):
    pack = _gloom_pack(tiny_pack_data)
    pruned = prune(pack, make_query(min_points=10))
    deco_ids = {d.id for d in pruned.decorations}
    assert FIXER_DECO_ID in deco_ids
    assert HARMFUL_FIXER_DECO_ID not in deco_ids


def test_allow_bad_off_is_infeasible_without_fixer(tiny_pack_data):
    pack = _gloom_pack(tiny_pack_data, with_fixer=False)
    query = make_query(min_points=10)
    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query, exclusions=[], time_limit_ms=2000
    )
    assert outcome.status == "infeasible"
    assert outcome.result is None


def test_allow_bad_off_uses_fixer_and_omits_penalty_from_active_skills(tiny_pack_data):
    pack = _gloom_pack(tiny_pack_data)
    query = make_query(min_points=10)
    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query, exclusions=[], time_limit_ms=2000
    )
    assert outcome.result is not None
    used = {a.decoration_id: a.count for a in outcome.result.decorations}
    assert used.get(FIXER_DECO_ID, 0) >= 1
    assert GLOOM_DOWN_ID not in {sid for sid, _ in outcome.result.active_skills}


def test_allow_bad_on_prefers_fixer_over_leaving_the_penalty(tiny_pack_data):
    pack = _gloom_pack(tiny_pack_data)
    query = make_query(min_points=10, allow_bad_skills=True)
    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query, exclusions=[], time_limit_ms=2000
    )
    assert outcome.result is not None
    used = {a.decoration_id: a.count for a in outcome.result.decorations}
    assert used.get(FIXER_DECO_ID, 0) >= 1
    assert GLOOM_DOWN_ID not in {sid for sid, _ in outcome.result.active_skills}


def test_allow_bad_on_reports_remaining_negative_skill_without_fixer(tiny_pack_data):
    pack = _gloom_pack(tiny_pack_data, with_fixer=False)
    query = make_query(min_points=10, allow_bad_skills=True)
    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query, exclusions=[], time_limit_ms=2000
    )
    assert outcome.result is not None
    assert (GLOOM_DOWN_ID, -10) in outcome.result.active_skills
