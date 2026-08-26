"""MockSearchService + fixture-backed names (phase0-contracts §6).

DELETED AT INTEGRATION: the integration session swaps this module for the real
SearchService (app.engine.service) plus repository-backed resolver/catalog, and
rewires them in the marked block in app/main.py.
"""

from app.domain.models import ArmorSetResult, Query, SearchPage

# --- tiny fixture (tests/fixtures/tiny_pack.py, verbatim data) ---
# HEAD  = [(1, 4, 0), (2, 2, 1), (3, 0, 2)]   # (piece_id, attack_pts, slots)
# BODY  = [(4, 3, 0), (5, 2, 1), (6, 0, 2)]
# ARMS  = [(7, 3, 1), (8, 1, 2), (9, 0, 0)]
# WAIST = [(10, 2, 1), (11, 1, 1), (12, 0, 2)]
# LEGS  = [(13, 3, 0), (14, 2, 1), (15, 0, 1)]
# DECORATIONS = [(101, 1, 1), (102, 2, 3)]    # (deco_id, size, attack_pts)
# One skill tree: Attack (tree_id 1); threshold Attack Up (S) = 10.
# All rarities 1; defense = slot index + 1.

_SLOT_WORDS = {0: "Helm", 1: "Mail", 2: "Vambraces", 3: "Faulds", 4: "Greaves"}
_TIERS = ("Leather", "Chain", "Hunter's")

_PIECES: dict[int, dict] = {}
for _slot, _ids in enumerate(((1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12), (13, 14, 15))):
    for _tier, _pid in enumerate(_ids):
        _PIECES[_pid] = {
            "name": f"{_TIERS[_tier]} {_SLOT_WORDS[_slot]}",
            "rarity": 1,
            "defense": _slot + 1,
        }

_DECORATION_NAMES = {101: "Attack Jewel 1", 102: "Attack Jewel 2"}
_SKILL_NAMES = {1: "Attack Up (S)"}


class FixtureResolver:
    """NameResolver over the tiny fixture (no database)."""

    def armor_piece(self, piece_id: int) -> dict:
        return _PIECES[piece_id]

    def decoration_name(self, decoration_id: int) -> str:
        return _DECORATION_NAMES[decoration_id]

    def skill_name(self, skill_id: int) -> str:
        return _SKILL_NAMES[skill_id]


class MockCatalog:
    """Form options for the index page, limited to the fixture's contents."""

    def list_games(self) -> list[dict]:
        return [
            {"code": "mhfu", "name": "Monster Hunter Freedom Unite", "generation": 2},
        ]

    def list_skill_trees(self, game: str) -> list[dict]:
        return [
            {
                "id": 1,
                "name": "Attack",
                "thresholds": [{"skill_id": 1, "name": "Attack Up (S)", "points": 10}],
            }
        ]


class MockSearchService:
    """Two canned pages: page 1 is the all-first-pieces set; page 2 is exhausted."""

    def __init__(self) -> None:
        self._counter = 0

    def start_search(self, session_id: str, query: Query) -> SearchPage:
        self._counter += 1
        result = ArmorSetResult(
            piece_ids=(1, 4, 7, 10, 13),
            alternates=((1,), (4,), (7,), (10,), (13,)),
            decorations=(),
            charm_id=None,
            active_skills=((1, 15),),
            spare_slots=(2, 0, 0),  # arms + waist each contribute one size-1 slot
            defense=15,  # 1+2+3+4+5 per the fixture's defense rule
        )
        return SearchPage(
            search_id=f"mock-{self._counter:04d}",
            results=(result,),
            partial=False,
            exhausted=False,
        )

    def load_more(self, session_id: str, search_id: str) -> SearchPage:
        return SearchPage(search_id=search_id, results=(), partial=False, exhausted=True)
