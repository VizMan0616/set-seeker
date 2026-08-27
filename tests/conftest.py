"""Shared app-level fixtures: a scratch database loaded with the tiny mhfu
pack (phase0-contracts §6) so the fully wired application can boot in tests."""

import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

# Make the repo root importable under any pytest invocation so
# `tests.fixtures.tiny_pack` (a namespace package) resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db import get_engine
from app.repository import tables
from app.repository.game_data import GameDataRepository
from tests.fixtures import tiny_pack

GAME_ID = 1
ATTACK_TREE_ID = 1
ATTACK_UP_S_SKILL_ID = 1

_SLOT_WORDS = {0: "Helm", 1: "Mail", 2: "Vambraces", 3: "Faulds", 4: "Greaves"}
_TIERS = ("Leather", "Chain", "Hunter's")
PIECE_NAMES = {
    piece_id: f"{_TIERS[tier]} {_SLOT_WORDS[slot]}"
    for slot, ids in enumerate(((1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12), (13, 14, 15)))
    for tier, piece_id in enumerate(ids)
}
DECORATION_NAMES = {101: "Attack Jewel 1", 102: "Attack Jewel 2"}


def load_tiny_pack(repo: GameDataRepository) -> None:
    """The §6 fixture as database rows; ids match tests/fixtures/tiny_pack.py."""
    repo.create_game(
        id=GAME_ID, code="mhfu", name="Monster Hunter Freedom Unite",
        generation=2, features=json.dumps({"talismans": False}),
    )
    repo.create_skill_tree(
        id=ATTACK_TREE_ID, game_id=GAME_ID, name_en="Attack", name_ja="Attack",
        category_tag="Offensive",
    )
    repo.create_skill(
        id=ATTACK_UP_S_SKILL_ID, tree_id=ATTACK_TREE_ID,
        name_en="Attack Up (S)", points=10,
    )
    repo.create_skill(
        id=2, tree_id=ATTACK_TREE_ID,
        name_en="Attack Up (Absurd)", points=99,
    )
    for slot, rows in enumerate((
        tiny_pack.HEAD, tiny_pack.BODY, tiny_pack.ARMS, tiny_pack.WAIST, tiny_pack.LEGS,
    )):
        for piece_id, attack_pts, slots in rows:
            repo.create_armor_piece(
                id=piece_id, game_id=GAME_ID, slot=slot,
                name_en=PIECE_NAMES[piece_id], rarity=1, slots=slots,
                gender=2, hunter_type=2, defense=slot + 1, max_defense=slot + 1,
                res_fire=0, res_water=0, res_ice=0, res_thunder=0, res_dragon=0,
            )
            if attack_pts:
                repo.set_armor_skill(
                    armor_id=piece_id, tree_id=ATTACK_TREE_ID, points=attack_pts,
                )
    for deco_id, size, pts in tiny_pack.DECORATIONS:
        repo.create_decoration(
            id=deco_id, game_id=GAME_ID, name_en=DECORATION_NAMES[deco_id],
            rarity=1, size=size,
        )
        repo.set_decoration_skill(
            decoration_id=deco_id, tree_id=ATTACK_TREE_ID, points=pts,
        )


@pytest.fixture()
def packed_db(tmp_path, monkeypatch):
    """Scratch SQLite DB with the tiny pack; app settings/engine point at it."""
    url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = create_engine(url)
    tables.metadata.create_all(engine)
    repo = GameDataRepository(engine)
    load_tiny_pack(repo)
    yield repo
    get_settings.cache_clear()
    get_engine.cache_clear()
