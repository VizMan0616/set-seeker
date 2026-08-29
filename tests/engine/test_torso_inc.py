"""Torso Inc / Torso Up: any-slot flag doubles the body (Athena GetInitialData)."""

from app.domain.models import Query, SkillRequest
from app.engine.data import BODY, HEAD, LEGS, ArmorPiece, PackData, SkillThreshold
from app.engine.pruning import prune
from app.engine.solver import solve_one

ATTACK_TREE = 1
ATTACK_UP_S = 1


def _piece(piece_id, slot, *, attack=0, slots=0, torso_inc=False) -> ArmorPiece:
    return ArmorPiece(
        id=piece_id,
        slot=slot,
        slots=slots,
        defense=1,
        rarity=1,
        skills=((ATTACK_TREE, attack),) if attack else (),
        torso_inc=torso_inc,
    )


def _pack(*pieces: ArmorPiece) -> PackData:
    return PackData(
        game="mhfu",
        game_id=1,
        pieces=pieces,
        decorations=(),
        skills=(SkillThreshold(id=ATTACK_UP_S, tree_id=ATTACK_TREE, points=10),),
        talismans=False,
    )


def _query(**overrides) -> Query:
    kwargs = dict(
        game="mhfu",
        skills=(SkillRequest(tree_id=ATTACK_TREE, min_points=10),),
        weapon_slots=0,
        gender="m",
        hunter_type="blademaster",
        hr=None,
        village_stars=None,
    )
    kwargs.update(overrides)
    return Query(**kwargs)


def test_torso_inc_on_legs_doubles_body_points():
    """Set1-style: Torso Up on greaves, not the chest."""
    pack = _pack(
        _piece(1, HEAD),
        _piece(2, BODY, attack=5),
        _piece(3, 2),
        _piece(4, 3),
        _piece(5, LEGS, torso_inc=True),
    )
    query = _query()
    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query,
        exclusions=[], time_limit_ms=2000,
    )
    assert outcome.status == "optimal"
    assert outcome.result is not None
    assert outcome.result.piece_ids[LEGS] == 5
    assert (ATTACK_UP_S, 10) in outcome.result.active_skills


def test_torso_inc_on_head_doubles_body_points():
    pack = _pack(
        _piece(1, HEAD, torso_inc=True),
        _piece(2, BODY, attack=5),
        _piece(3, 2),
        _piece(4, 3),
        _piece(5, LEGS),
    )
    query = _query()
    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query,
        exclusions=[], time_limit_ms=2000,
    )
    assert outcome.status == "optimal"
    assert outcome.result is not None
    assert outcome.result.piece_ids[HEAD] == 1


def test_allow_torso_inc_off_excludes_the_flagged_piece():
    pack = _pack(
        _piece(1, HEAD),
        _piece(2, BODY, attack=5),
        _piece(3, 2),
        _piece(4, 3),
        _piece(5, LEGS, torso_inc=True),
    )
    query = _query(allow_torso_inc=False)
    pruned = prune(pack, query)
    assert all(
        not m.torso_inc
        for slot in pruned.classes
        for c in slot
        for m in c.members
    )
    outcome = solve_one(
        pack=pack, pruned=pruned, query=query,
        exclusions=[], time_limit_ms=2000,
    )
    assert outcome.status == "infeasible"
    assert outcome.result is None
