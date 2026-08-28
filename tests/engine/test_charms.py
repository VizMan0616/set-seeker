"""Charm variable: inventory, generated envelopes, weakest-charm objective."""

from app.domain.models import CharmSpec
from app.engine.charms import charm_candidates
from app.engine.data import CharmTypeSpec, PackData
from app.engine.pruning import domain_snapshot, prune
from app.engine.solver import solve_one
from tests.engine.conftest import ATTACK_TREE, make_query, make_tiny_pack


def _talisman_pack(**overrides) -> PackData:
    base = make_tiny_pack()
    return PackData(
        game="mhp3",
        game_id=1,
        pieces=base.pieces,
        decorations=base.decorations,
        skills=base.skills,
        talismans=True,
        charm_types=overrides.get("charm_types", ()),
    )


def test_none_charm_when_armor_suffices():
    pack = _talisman_pack()
    query = make_query(
        min_points=10,
        game="mhp3",
        use_generated_charms=False,
        user_charms=(CharmSpec(id=7, slots=1, skills=((ATTACK_TREE, 6),)),),
    )
    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query, exclusions=[], time_limit_ms=2000
    )
    assert outcome.result is not None
    assert outcome.result.charm_id is None


def test_user_charm_completes_otherwise_impossible_query():
    pack = _talisman_pack()
    charm = CharmSpec(id=3, slots=0, skills=((ATTACK_TREE, 10),))
    query = make_query(
        min_points=25,
        game="mhp3",
        use_generated_charms=False,
        user_charms=(charm,),
    )
    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query, exclusions=[], time_limit_ms=2000
    )
    assert outcome.result is not None
    assert outcome.result.charm_id == 3
    assert outcome.result.charm_skills == ((ATTACK_TREE, 10),)


def test_generated_charm_from_type_envelope():
    pack = _talisman_pack(
        charm_types=(
            CharmTypeSpec(
                code="mystery",
                max_slots=1,
                skill1=((ATTACK_TREE, 0, 6),),
                slot_thresholds=((0, 0), (1, 1), (5, 0), (10, 0)),
            ),
        )
    )
    query = make_query(min_points=20, game="mhp3", user_charms=())
    outcome = solve_one(
        pack=pack,
        pruned=prune(pack, query),
        query=query,
        exclusions=[],
        time_limit_ms=2000,
    )
    assert outcome.result is not None
    assert outcome.result.charm_id is not None and outcome.result.charm_id < 0
    attack = dict(outcome.result.charm_skills).get(ATTACK_TREE, 0)
    assert 1 <= attack <= 6
    # fulfillment int(pts / (6/10)): pts≥5 → rank≥8 → 0 slots
    if attack >= 5:
        assert outcome.result.charm_slots == 0
    else:
        assert outcome.result.charm_slots <= 1


def test_generated_candidates_obey_max_and_slot_fulfillment():
    pack = _talisman_pack(
        charm_types=(
            CharmTypeSpec(
                code="mystery",
                max_slots=3,
                skill1=((ATTACK_TREE, 0, 4),),
                slot_thresholds=((0, 0), (1, 1), (2, 1), (10, 0)),
            ),
        )
    )
    query = make_query(min_points=10, game="mhp3", user_charms=())
    generated = [c for c in charm_candidates(pack, query) if c.id < 0]
    assert generated
    assert all(
        (not c.skills or (c.skills[0][0] == ATTACK_TREE and 1 <= c.skills[0][1] <= 4))
        for c in generated
    )
    # Attack +4: fulfillment int(4 / 0.4) = 10 → 0 slots only
    assert all(c.slots == 0 for c in generated if c.skills == ((ATTACK_TREE, 4),))
    assert not any(c.slots >= 2 for c in generated)
    assert not any(pts > 4 for _, pts in (s for c in generated for s in c.skills))


def test_exclusions_include_charm_so_same_armor_can_recur():
    pack = _talisman_pack()
    charms = (
        CharmSpec(id=11, slots=0, skills=((ATTACK_TREE, 10),)),
        CharmSpec(id=12, slots=3, skills=((ATTACK_TREE, 10),)),
    )
    query = make_query(
        min_points=25, game="mhp3", use_generated_charms=False, user_charms=charms
    )
    pruned = prune(pack, query)
    first = solve_one(
        pack=pack, pruned=pruned, query=query, exclusions=[], time_limit_ms=2000
    )
    assert first.result is not None
    charm = first.result.charm_id if first.result.charm_id is not None else 0
    second = solve_one(
        pack=pack,
        pruned=pruned,
        query=query,
        exclusions=[(*first.result.piece_ids, charm)],
        time_limit_ms=2000,
    )
    if second.result is not None:
        assert first.result.charm_id != second.result.charm_id or (
            first.result.piece_ids != second.result.piece_ids
        )


def test_domain_snapshot_lists_user_charms(tiny_pack_data):
    pack = _talisman_pack()
    query = make_query(
        min_points=10,
        game="mhp3",
        user_charms=(CharmSpec(id=9, slots=2, skills=((ATTACK_TREE, 4),)),),
    )
    pruned = prune(pack, query)
    snap = domain_snapshot(pack, pruned)
    assert snap["kinds"]["charms"]["rel_ids"] == [9]


def test_mhfu_pack_still_has_no_charm_kind(tiny_pack_data):
    pruned = prune(tiny_pack_data, make_query(min_points=10))
    assert "charms" not in domain_snapshot(tiny_pack_data, pruned)["kinds"]
