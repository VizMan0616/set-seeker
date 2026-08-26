"""Unit tests for the pruning pipeline (engine-spec.md §1)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.engine.data import ARMS, HEAD, LEGS, ArmorPiece
from app.engine.pruning import (
    dominance_prune,
    equivalence_collapse,
    prune,
)
from tests.engine.conftest import ATTACK_TREE, make_query


def _piece(piece_id, slot, slots, attack, defense=10, **kw) -> ArmorPiece:
    return ArmorPiece(
        id=piece_id,
        slot=slot,
        slots=slots,
        defense=defense,
        rarity=1,
        skills=((ATTACK_TREE, attack),) if attack else (),
        **kw,
    )


def test_relevance_filter_drops_pointless_submax_slot_pieces(tiny_pack_data):
    pruned = prune(tiny_pack_data, make_query(min_points=10))

    kept_ids = {c.representative.id for slot in pruned.classes for c in slot}
    # Arms 9 (0 pts, 0 slots) and legs 15 (0 pts, 1 slot < max 2) are irrelevant.
    assert 9 not in kept_ids
    assert 15 not in kept_ids
    # Waist 12 (0 pts, 2 slots = max for its slot) stays: slots are currency.
    assert 12 in kept_ids
    # Both decorations grant Attack and survive.
    assert {d.id for d in pruned.decorations} == {101, 102}


def test_dominance_prune_drops_dominated_pieces():
    pieces = [
        _piece(1, HEAD, slots=1, attack=2),
        _piece(2, HEAD, slots=1, attack=1),  # dominated by 1
        _piece(3, HEAD, slots=2, attack=0),  # not dominated: more slots
    ]
    kept = dominance_prune(pieces, (ATTACK_TREE,))
    assert {p.id for p in kept} == {1, 3}


def test_equivalence_collapse_groups_identical_stats_and_keeps_members():
    pieces = [
        _piece(1, ARMS, slots=1, attack=2, defense=10),
        _piece(2, ARMS, slots=1, attack=2, defense=20),  # same stats, more defense
        _piece(3, ARMS, slots=1, attack=2, defense=15, torso_inc=True),
    ]
    classes = equivalence_collapse(pieces, (ATTACK_TREE,))

    assert len(classes) == 2  # torso Inc splits the second class
    plain = next(c for c in classes if not c.representative.torso_inc)
    assert plain.representative.id == 2  # highest defense represents the class
    assert [m.id for m in plain.members] == [2, 1]


def test_prune_hard_filters_gender_and_event(tiny_pack_data):
    pieces = list(tiny_pack_data.pieces) + [
        _piece(90, LEGS, slots=3, attack=5, gender=1),  # female-only
        _piece(91, LEGS, slots=3, attack=5, is_event=True),
    ]
    pack = tiny_pack_data.__class__(
        game=tiny_pack_data.game,
        game_id=tiny_pack_data.game_id,
        pieces=tuple(pieces),
        decorations=tiny_pack_data.decorations,
        skills=tiny_pack_data.skills,
        talismans=tiny_pack_data.talismans,
    )
    pruned = prune(pack, make_query(min_points=10, gender="m"))

    legs_ids = {c.representative.id for c in pruned.classes[LEGS]}
    assert 90 not in legs_ids
    assert 91 not in legs_ids

    pruned_event = prune(pack, make_query(min_points=10, gender="f", allow_event=True))
    # 90 and 91 have identical stats, so they share an equivalence class;
    # both must appear in the member list even though only one represents it.
    legs_member_ids = {m.id for c in pruned_event.classes[LEGS] for m in c.members}
    assert {90, 91} <= legs_member_ids


def _pack_with_extra_pieces(tiny_pack_data, extra):
    return tiny_pack_data.__class__(
        game=tiny_pack_data.game,
        game_id=tiny_pack_data.game_id,
        pieces=tuple(list(tiny_pack_data.pieces) + extra),
        decorations=tiny_pack_data.decorations,
        skills=tiny_pack_data.skills,
        talismans=tiny_pack_data.talismans,
    )


def test_progression_caps_use_or_availability(tiny_pack_data):
    """Legacy Armor.cpp:102: excluded only when BOTH progression caps are exceeded.

    10 is the sentinel for "not obtainable via this path" (both caps max at 9),
    so G-rank pieces carry village_stars=10 and village pieces hr_required=10.
    """
    pack = _pack_with_extra_pieces(tiny_pack_data, [
        _piece(92, LEGS, slots=3, attack=5, hr_required=9, village_stars=10),   # HR path
        _piece(93, LEGS, slots=3, attack=5, hr_required=10, village_stars=4),  # village path
        _piece(94, LEGS, slots=3, attack=5, hr_required=10, village_stars=10), # neither
    ])
    pruned = prune(pack, make_query(min_points=10, hr=9, village_stars=9))

    legs_member_ids = {m.id for c in pruned.classes[LEGS] for m in c.members}
    assert 92 in legs_member_ids      # reachable via HR
    assert 93 in legs_member_ids      # reachable via village
    assert 94 not in legs_member_ids  # exceeds both caps


def test_progression_caps_close_the_other_path(tiny_pack_data):
    pack = _pack_with_extra_pieces(tiny_pack_data, [
        _piece(92, LEGS, slots=3, attack=5, hr_required=9, village_stars=10),
        _piece(93, LEGS, slots=3, attack=5, hr_required=10, village_stars=4),
    ])
    pruned = prune(pack, make_query(min_points=10, hr=9, village_stars=3))

    legs_member_ids = {m.id for c in pruned.classes[LEGS] for m in c.members}
    assert 92 in legs_member_ids       # HR path still open
    assert 93 not in legs_member_ids   # village 4 > cap 3, HR sentinel 10 > 9


def test_uncapped_progression_paths_admit_everything(tiny_pack_data):
    pack = _pack_with_extra_pieces(tiny_pack_data, [
        _piece(92, LEGS, slots=3, attack=5, hr_required=9, village_stars=10),
        _piece(93, LEGS, slots=3, attack=5, hr_required=10, village_stars=4),
    ])
    pruned = prune(pack, make_query(min_points=10))  # both caps None = uncapped

    legs_member_ids = {m.id for c in pruned.classes[LEGS] for m in c.members}
    assert {92, 93} <= legs_member_ids


def test_village_only_decoration_survives_hr_cap(tiny_pack_data):
    """Village-path jewels (hr sentinel 10) must not vanish from capped searches."""
    from app.engine.data import Decoration

    pack = tiny_pack_data.__class__(
        game=tiny_pack_data.game,
        game_id=tiny_pack_data.game_id,
        pieces=tiny_pack_data.pieces,
        decorations=tiny_pack_data.decorations
        + (Decoration(id=199, size=1, skills=((ATTACK_TREE, 1),),
                      hr_required=10, village_stars=4),),
        skills=tiny_pack_data.skills,
        talismans=tiny_pack_data.talismans,
    )
    pruned = prune(pack, make_query(min_points=10, hr=9, village_stars=9))
    assert 199 in {d.id for d in pruned.decorations}

    pruned_low = prune(pack, make_query(min_points=10, hr=1, village_stars=1))
    assert 199 not in {d.id for d in pruned_low.decorations}


def test_prune_bad_skill_thresholds_follow_allow_bad_skills(tiny_pack_data):
    from app.engine.data import SkillThreshold

    pack = tiny_pack_data.__class__(
        game=tiny_pack_data.game,
        game_id=tiny_pack_data.game_id,
        pieces=tiny_pack_data.pieces,
        decorations=tiny_pack_data.decorations,
        skills=tiny_pack_data.skills
        + (SkillThreshold(id=99, tree_id=ATTACK_TREE, points=-10, is_negative=True),),
        talismans=tiny_pack_data.talismans,
    )
    assert prune(pack, make_query(min_points=10)).bad_tree_thresholds == ((ATTACK_TREE, -10),)
    assert (
        prune(pack, make_query(min_points=10, allow_bad_skills=True)).bad_tree_thresholds == ()
    )
