"""Charm variable: inventory, generated envelopes, weakest-charm objective."""

from app.domain.models import CharmSpec, SkillRequest
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


def test_one_skill_charms_ignore_skill2_envelope():
    """Skill 2 maxima (+10) must not appear on a one-skill (skill-1) charm."""
    other = 99
    pack = _talisman_pack(
        charm_types=(
            CharmTypeSpec(
                code="timeworn",
                max_slots=0,
                skill1=((other, 0, 6),),
                skill2=((ATTACK_TREE, -10, 10),),
            ),
        )
    )
    query = make_query(min_points=10, game="mhp3", user_charms=())
    generated = [c for c in charm_candidates(pack, query) if c.id < 0]
    assert all(not c.skills for c in generated)


def test_two_skill_puts_high_max_on_slot_two():
    other = 99
    pack = _talisman_pack(
        charm_types=(
            CharmTypeSpec(
                code="timeworn",
                max_slots=0,
                skill1=((other, 0, 6),),
                skill2=((ATTACK_TREE, -10, 10),),
            ),
        )
    )
    query = make_query(
        min_points=10,
        game="mhp3",
        charm_mode="two_skill",
        user_charms=(),
        skills=(
            SkillRequest(tree_id=ATTACK_TREE, min_points=10),
            SkillRequest(tree_id=other, min_points=1),
        ),
    )
    generated = [c for c in charm_candidates(pack, query) if c.id < 0 and len(c.skills) == 2]
    assert generated
    assert all(c.skills[0][0] == other and c.skills[1][0] == ATTACK_TREE for c in generated)
    assert max(c.skills[1][1] for c in generated) == 10
    assert max(c.skills[0][1] for c in generated) == 6
    assert all(c.skills[1][1] in (-10, 1, 10) for c in generated)


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
    query = make_query(min_points=25, game="mhp3", use_generated_charms=False, user_charms=charms)
    pruned = prune(pack, query)
    first = solve_one(pack=pack, pruned=pruned, query=query, exclusions=[], time_limit_ms=2000)
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
        charm_mode="inventory",
        use_generated_charms=False,
        user_charms=(CharmSpec(id=9, slots=2, skills=((ATTACK_TREE, 4),)),),
    )
    pruned = prune(pack, query)
    snap = domain_snapshot(pack, pruned)
    assert snap["kinds"]["charms"]["rel_ids"] == [9]


def test_two_skill_domain_is_corners_not_full_grid():
    trees = (ATTACK_TREE, 2, 3, 4, 5, 6)
    pack = _talisman_pack(
        charm_types=(
            CharmTypeSpec(
                code="timeworn",
                max_slots=0,
                skill1=tuple((t, 0, 7) for t in trees),
                skill2=tuple((t, -10, 10) for t in trees),
            ),
        )
    )
    query = make_query(
        min_points=10,
        game="mhp3",
        charm_mode="two_skill",
        user_charms=(),
        skills=tuple(SkillRequest(tree_id=t, min_points=10) for t in trees),
    )
    two = [c for c in charm_candidates(pack, query) if c.id < 0 and len(c.skills) == 2]
    assert two
    assert len(two) < 400


def test_mhfu_pack_still_has_no_charm_kind(tiny_pack_data):
    pruned = prune(tiny_pack_data, make_query(min_points=10))
    assert "charms" not in domain_snapshot(tiny_pack_data, pruned)["kinds"]


def _two_tree_pack() -> PackData:
    other = 99
    return _talisman_pack(
        charm_types=(
            CharmTypeSpec(
                code="timeworn",
                max_slots=3,
                skill1=((ATTACK_TREE, 0, 6), (other, 0, 6)),
                skill2=((ATTACK_TREE, -10, 10), (other, -10, 10)),
            ),
        )
    )


def test_charm_mode_none_is_only_none():
    pack = _two_tree_pack()
    query = make_query(
        min_points=10,
        game="mhp3",
        charm_mode="none",
        user_charms=(CharmSpec(id=3, slots=1, skills=((ATTACK_TREE, 4),)),),
    )
    ids = [c.id for c in charm_candidates(pack, query)]
    assert ids == [0]


def test_charm_mode_inventory_skips_generated():
    pack = _two_tree_pack()
    owned = CharmSpec(id=3, slots=1, skills=((ATTACK_TREE, 4),))
    query = make_query(
        min_points=10,
        game="mhp3",
        charm_mode="inventory",
        use_generated_charms=False,
        user_charms=(owned,),
    )
    ids = [c.id for c in charm_candidates(pack, query)]
    assert ids == [0, 3]


def test_charm_mode_slotted_has_no_skill_rows():
    pack = _two_tree_pack()
    query = make_query(min_points=10, game="mhp3", charm_mode="slotted", user_charms=())
    generated = [c for c in charm_candidates(pack, query) if c.id < 0]
    assert generated
    assert all(not c.skills for c in generated)
    assert max(c.slots for c in generated) == 3


def test_charm_mode_one_skill_skips_two_tree_pairs():
    pack = _two_tree_pack()
    query = make_query(
        min_points=10,
        game="mhp3",
        charm_mode="one_skill",
        user_charms=(),
        skills=(
            SkillRequest(tree_id=ATTACK_TREE, min_points=10),
            SkillRequest(tree_id=99, min_points=1),
        ),
    )
    generated = [c for c in charm_candidates(pack, query) if c.id < 0]
    assert any(len(c.skills) == 1 for c in generated)
    assert all(len(c.skills) <= 1 for c in generated)


def test_charm_mode_two_skill_skips_one_skill_point_grid():
    pack = _two_tree_pack()
    query = make_query(
        min_points=10,
        game="mhp3",
        charm_mode="two_skill",
        user_charms=(),
        skills=(
            SkillRequest(tree_id=ATTACK_TREE, min_points=10),
            SkillRequest(tree_id=99, min_points=1),
        ),
    )
    generated = [c for c in charm_candidates(pack, query) if c.id < 0]
    assert any(len(c.skills) == 2 for c in generated)
    assert all(len(c.skills) != 1 for c in generated)
