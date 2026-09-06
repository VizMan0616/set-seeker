"""Solver-level regression on the real MHFU pack (phase0-contracts.md §9).

Encodes the first real-user stress query: Expert 20 + Artisan 10 + Sharpness 10
with a 1-slot weapon at HR 9 / village 9-star. Feasible in-game without a charm
(e.g. Skull Face / Ceanataur U / Ceanataur Z mixes); an AND-progression filter
bug (sentinel value 10 = "not obtainable via this path") made the engine report
no sets. Legacy availability is an OR over the HR and village paths
(sources/MHFU-ASS/MH Armor/Armor.cpp:102).
"""

from app.domain.models import Query, SkillRequest
from app.engine.pruning import prune
from app.engine.solver import solve_one
from app.pack_loader import PackLoader


def _stress_query(tree_ids):
    return Query(
        game="mhfu",
        skills=(
            SkillRequest(tree_ids["Expert"], 20),  # Critical Eye +3
            SkillRequest(tree_ids["Artisan"], 10),  # Sharpness +1
            SkillRequest(tree_ids["Sharpness"], 10),  # Sharp Sword
        ),
        weapon_slots=1,
        gender="m",
        hunter_type="blademaster",
        hr=9,
        village_stars=9,
    )


def test_expert_artisan_sharpness_stress_query_is_feasible(etl_db):
    repo, game_id, _ = etl_db
    pack = PackLoader(repo)("mhfu")
    tree_ids = {t["name_en"]: t["id"] for t in repo.list_skill_trees(game_id)}
    query = _stress_query(tree_ids)

    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query, exclusions=[], time_limit_ms=30000
    )

    assert outcome.status == "optimal"
    result = outcome.result
    assert result is not None and result.charm_id is None

    # The solver's own accounting: active_skills is (skill_id, points achieved).
    tree_of_skill = {sk.id: sk.tree_id for sk in pack.skills}
    achieved = {tree_of_skill[skill_id]: pts for skill_id, pts in result.active_skills}
    assert achieved[tree_ids["Expert"]] >= 20
    assert achieved[tree_ids["Artisan"]] >= 10
    assert achieved[tree_ids["Sharpness"]] >= 10


def test_g_rank_sentinel_pieces_survive_maxed_caps(etl_db):
    """Kaiser Mail X (HR 9 / village sentinel 10) is G-rank HR-obtainable and
    must stay in the search space at HR 9 / village 9-star."""
    repo, game_id, _ = etl_db
    pack = PackLoader(repo)("mhfu")
    tree_ids = {t["name_en"]: t["id"] for t in repo.list_skill_trees(game_id)}
    query = _stress_query(tree_ids)
    pruned = prune(pack, query)

    kaiser_id = next(
        p["id"]
        for p in repo.list_armor_pieces(game_id, slot=1, allow_event=True)
        if p["name_en"] == "Kaiser Mail X"
    )
    body_member_ids = {m.id for c in pruned.classes[1] for m in c.members}
    assert kaiser_id in body_member_ids

    # Village-only jewels keep their path too (Artisan Jewel: HR sentinel 10,
    # village 4-star).
    artisan_id = next(
        d["id"]
        for d in repo.list_decorations(game_id, allow_event=True)
        if d["name_en"] == "Artisan Jewel"
    )
    assert artisan_id in {d.id for d in pruned.decorations}
