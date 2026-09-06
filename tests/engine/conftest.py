import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

# Make the repo root importable under any pytest invocation so
# `tests.fixtures.tiny_pack` (a namespace package) resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.domain.models import Query, SkillRequest
from app.engine.data import ArmorPiece, Decoration, PackData, SkillThreshold
from app.engine.service import CpSatSearchService
from app.repository import tables
from app.repository.user_data import UserDataRepository
from tests.fixtures import tiny_pack

ATTACK_TREE = 1
ATTACK_UP_S_SKILL_ID = 1  # threshold row: Attack Up (S) at 10 points

SLOT_ROWS = (tiny_pack.HEAD, tiny_pack.BODY, tiny_pack.ARMS, tiny_pack.WAIST, tiny_pack.LEGS)


def make_tiny_pack() -> PackData:
    """PackData from the verbatim fixture; defense = slot index + 1 (phase0 §6)."""
    pieces = []
    for slot, rows in enumerate(SLOT_ROWS):
        for piece_id, attack_pts, slots in rows:
            pieces.append(
                ArmorPiece(
                    id=piece_id,
                    slot=slot,
                    slots=slots,
                    defense=slot + 1,
                    rarity=1,
                    skills=((ATTACK_TREE, attack_pts),) if attack_pts else (),
                )
            )
    decorations = tuple(
        Decoration(id=deco_id, size=size, skills=((ATTACK_TREE, pts),))
        for deco_id, size, pts in tiny_pack.DECORATIONS
    )
    skills = (SkillThreshold(id=ATTACK_UP_S_SKILL_ID, tree_id=ATTACK_TREE, points=10),)
    return PackData(
        game="mhfu",
        game_id=1,
        pieces=tuple(pieces),
        decorations=decorations,
        skills=skills,
        talismans=False,
    )


def make_query(min_points: int = 10, **overrides) -> Query:
    kwargs = {
        "game": "mhfu",
        "skills": (SkillRequest(tree_id=ATTACK_TREE, min_points=min_points),),
        "weapon_slots": 0,
        "gender": "m",
        "hunter_type": "blademaster",
        "hr": None,
        "village_stars": None,
    }
    kwargs.update(overrides)
    return Query(**kwargs)


@pytest.fixture
def tiny_pack_data() -> PackData:
    return make_tiny_pack()


@pytest.fixture
def user_data_repo():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            tables.games.insert().values(
                id=1,
                code="mhfu",
                name="Monster Hunter Freedom Unite",
                generation=2,
                features="{}",
            )
        )
    return UserDataRepository(engine)


@pytest.fixture
def search_service(user_data_repo, tiny_pack_data) -> CpSatSearchService:
    return CpSatSearchService(
        user_data_repo,
        lambda game: tiny_pack_data,
        time_limit_ms=2000,
    )
