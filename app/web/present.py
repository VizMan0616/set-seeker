"""Build the phase0 §5 template context from engine results.

The engine speaks ids; the web layer resolves them to display names through a
NameResolver. The mock resolver (app.web.mock) reads the tiny fixture; the real
one wraps repository.game_data at integration time.
"""

from typing import Any, Protocol

from app.domain.models import ArmorSetResult, Query, SearchPage
from app.engine.data import ARMOR_SLOT_KINDS, PackData
from app.engine.pruning import PrunedPack, domain_snapshot

SLOT_ORDER = ("head", "body", "arms", "waist", "legs")

KIND_LABELS = {
    "head": "Head",
    "body": "Chest",
    "arms": "Arms",
    "waist": "Waist",
    "legs": "Legs",
    "decorations": "Jewels",
    "charms": "Charms",
    "weapons": "Weapons",
}


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


def advanced_columns(
    pack: PackData, pruned: PrunedPack, query: Query, resolver: NameResolver
) -> list[dict[str, Any]]:
    """One tab per snapshot kind; checked = current solver rel."""
    excluded_p = set(query.excluded_piece_ids)
    forced_p = set(query.forced_piece_ids)
    excluded_d = set(query.excluded_decoration_ids)
    forced_d = set(query.forced_decoration_ids)
    columns: list[dict[str, Any]] = []
    for kind, ids in domain_snapshot(pack, pruned)["kinds"].items():
        skyline = set(ids["rel_ids"])
        items: list[dict[str, Any]] = []
        if kind in ARMOR_SLOT_KINDS:
            input_name = "rel_piece_id"
            for piece_id in ids["inf_ids"]:
                items.append(
                    {
                        "id": piece_id,
                        "name": resolver.armor_piece(piece_id)["name"],
                        "checked": (
                            (piece_id in skyline and piece_id not in excluded_p)
                            or piece_id in forced_p
                        ),
                        "skyline": piece_id in skyline,
                    }
                )
        elif kind == "decorations":
            input_name = "rel_decoration_id"
            for deco_id in ids["inf_ids"]:
                items.append(
                    {
                        "id": deco_id,
                        "name": resolver.decoration_name(deco_id),
                        "checked": (
                            (deco_id in skyline and deco_id not in excluded_d)
                            or deco_id in forced_d
                        ),
                        "skyline": deco_id in skyline,
                    }
                )
        else:
            input_name = f"rel_{kind.rstrip('s')}_id"
        columns.append(
            {
                "key": kind,
                "label": KIND_LABELS.get(kind, kind),
                "input_name": input_name,
                "rows": items,
            }
        )
    return columns


def page_context(
    page: SearchPage,
    resolver: NameResolver,
    *,
    advanced: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The exact template context settled in phase0-contracts §5."""
    return {
        "search_id": page.search_id,
        "results": [_result_context(r, resolver) for r in page.results],
        "partial": page.partial,
        "exhausted": page.exhausted,
        "shown_count": page.shown_count,
        "remaining_count": page.remaining_count,
        "advanced_columns": advanced or [],
    }
