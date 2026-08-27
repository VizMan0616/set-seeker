"""Build the phase0 §5 template context from engine results.

The engine speaks ids; the web layer resolves them to display names through a
NameResolver. The mock resolver (app.web.mock) reads the tiny fixture; the real
one wraps repository.game_data at integration time.
"""

from typing import Any, Protocol

from app.domain.models import ArmorSetResult, SearchPage

SLOT_ORDER = ("head", "body", "arms", "waist", "legs")


class NameResolver(Protocol):
    def armor_piece(self, piece_id: int) -> dict[str, Any]:
        """Return {"name": str, "rarity": int, "defense": int}."""
        ...

    def decoration_name(self, decoration_id: int) -> str: ...

    def skill_name(self, skill_id: int) -> str: ...


class Catalog(Protocol):
    """Form options for the index page (games + skill trees)."""

    def list_games(self) -> list[dict[str, Any]]: ...

    def list_skill_trees(self, game: str) -> list[dict[str, Any]]: ...

    def list_search_catalog(self, game: str) -> dict[str, Any]: ...


def _result_context(result: ArmorSetResult, resolver: NameResolver) -> dict[str, Any]:
    pieces = []
    for slot, piece_id, alternates in zip(
        SLOT_ORDER, result.piece_ids, result.alternates, strict=True
    ):
        piece = resolver.armor_piece(piece_id)
        pieces.append(
            {
                "slot": slot,
                "name": piece["name"],
                "rarity": piece["rarity"],
                "defense": piece["defense"],
                "alternates": [
                    {"id": alt_id, "name": resolver.armor_piece(alt_id)["name"]}
                    for alt_id in alternates
                ],
            }
        )
    return {
        "pieces": pieces,
        "decorations": [
            {"name": resolver.decoration_name(d.decoration_id), "count": d.count}
            for d in result.decorations
        ],
        "charm": None,  # mhfu: always None (pack flag talismans: false)
        "active_skills": [
            {"name": resolver.skill_name(skill_id), "points": points}
            for skill_id, points in result.active_skills
        ],
        "spare_slots": list(result.spare_slots),
        "defense": result.defense,
    }


def page_context(page: SearchPage, resolver: NameResolver) -> dict[str, Any]:
    """The exact template context settled in phase0-contracts §5."""
    return {
        "search_id": page.search_id,
        "results": [_result_context(r, resolver) for r in page.results],
        "partial": page.partial,
        "exhausted": page.exhausted,
        "shown_count": page.shown_count,
        "remaining_count": page.remaining_count,
    }
