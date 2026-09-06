"""In-memory pack data the engine operates on.

The engine is pure (phase0-contracts.md §3): it sees ids and numbers, never
database rows. The web/integration layer is responsible for loading rows via
``app.repository.game_data`` and building a ``PackData``; tests build one
directly from ``tests/fixtures/tiny_pack.py``.

Gender / hunter-type codes mirror ``app.repository.tables``: 0 = male /
blademaster, 1 = female / gunner, 2 = both.
"""

from dataclasses import dataclass

HEAD, BODY, ARMS, WAIST, LEGS = range(5)
SLOT_COUNT = 5
ARMOR_SLOT_KINDS = ("head", "body", "arms", "waist", "legs")


@dataclass(frozen=True)
class ArmorPiece:
    id: int
    slot: int  # 0=head .. 4=legs
    slots: int  # decoration sockets, 0..3
    defense: int
    rarity: int
    skills: tuple[tuple[int, int], ...] = ()  # (tree_id, signed points)
    torso_inc: bool = False
    gender: int = 2
    hunter_type: int = 2
    hr_required: int = 0
    village_stars: int = 0
    is_event: bool = False
    is_dummy: bool = False
    res_fire: int = 0
    res_water: int = 0
    res_ice: int = 0
    res_thunder: int = 0
    res_dragon: int = 0


@dataclass(frozen=True)
class Decoration:
    id: int
    size: int  # 1..3 slots occupied on a single piece
    skills: tuple[tuple[int, int], ...] = ()  # (tree_id, signed points)
    rarity: int = 1
    hr_required: int = 0
    village_stars: int = 0
    is_event: bool = False


@dataclass(frozen=True)
class SkillThreshold:
    id: int
    tree_id: int
    points: int  # signed; negative rows are bad skills
    is_negative: bool = False


@dataclass(frozen=True)
class CharmTypeSpec:
    """Legal envelopes for one charm rarity/type (extracted RNG / CSV tables)."""

    code: str
    max_slots: int
    skill1: tuple[tuple[int, int, int], ...] = ()  # (tree_id, min_points, max_points)
    skill2: tuple[tuple[int, int, int], ...] = ()
    # (fulfillment, max_slots) from *_slots.csv / charm_slot_thresholds.
    slot_thresholds: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class PackData:
    game: str  # pack id, e.g. "mhfu"
    game_id: int  # games.id, for search_states rows
    pieces: tuple[ArmorPiece, ...] = ()
    decorations: tuple[Decoration, ...] = ()
    skills: tuple[SkillThreshold, ...] = ()
    talismans: bool = False  # pack flag; False for mhfu
    weapon_search: bool = False  # pack flag; weapons as a 6th search dimension
    charm_types: tuple[CharmTypeSpec, ...] = ()
