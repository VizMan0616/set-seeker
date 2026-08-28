"""Build the phase0 §5 template context from engine results.

The engine speaks ids; the web layer resolves them to display names through a
NameResolver. The mock resolver (app.web.mock) reads the tiny fixture; the real
one wraps repository.game_data at integration time.
"""

from dataclasses import replace
from itertools import product
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

    def skill_tree_name(self, tree_id: int) -> str: ...


class Catalog(Protocol):
    """Form options for the index page (games + skill trees)."""

    def list_games(self) -> list[dict[str, Any]]: ...

    def list_skill_trees(self, game: str) -> list[dict[str, Any]]: ...

    def list_search_catalog(self, game: str) -> dict[str, Any]: ...


def _format_charm(slots: int, skills: tuple[tuple[int, int], ...], resolver: NameResolver) -> str:
    pips = "O" * slots + "-" * (3 - slots)
    if not skills:
        return f"{pips} (slots)"
    parts = [f"{resolver.skill_tree_name(tree)} {pts:+d}" for tree, pts in skills]
    return f"{', '.join(parts)} {pips}"


def _charm_label(result: ArmorSetResult, resolver: NameResolver) -> str | None:
    if result.charm_id is None:
        return None
    return _format_charm(result.charm_slots, result.charm_skills, resolver)


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
        "charm": _charm_label(result, resolver),
        "active_skills": [
            {"name": resolver.skill_name(skill_id), "points": points}
            for skill_id, points in result.active_skills
        ],
        "spare_slots": list(result.spare_slots),
        "defense": result.defense,
    }


def expand_equivalent_results(
    result: ArmorSetResult, resolver: NameResolver
) -> tuple[ArmorSetResult, ...]:
    """One ArmorSetResult per equivalence-class combination (Athena expansion)."""
    members = [
        alts if alts else (piece_id,)
        for piece_id, alts in zip(result.piece_ids, result.alternates, strict=True)
    ]
    expanded: list[ArmorSetResult] = []
    for combo in product(*members):
        defense = sum(resolver.armor_piece(pid)["defense"] for pid in combo)
        expanded.append(
            replace(
                result,
                piece_ids=(combo[0], combo[1], combo[2], combo[3], combo[4]),
                alternates=tuple((pid,) for pid in combo),
                defense=defense,
            )
        )
    return tuple(expanded)


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
        elif kind == "charms":
            input_name = "rel_charm_id"
            excluded_c = set(query.excluded_charm_ids)
            forced_c = set(query.forced_charm_ids)
            by_id = {c.id: c for c in pruned.catalog_charms or pruned.charms}
            for charm_id in ids["inf_ids"]:
                spec = by_id.get(charm_id)
                items.append(
                    {
                        "id": charm_id,
                        "name": _format_charm(
                            spec.slots if spec else 0,
                            spec.skills if spec else (),
                            resolver,
                        ),
                        "checked": (
                            (charm_id in skyline and charm_id not in excluded_c)
                            or charm_id in forced_c
                        ),
                        "skyline": charm_id in skyline,
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
    expand_equivalents: bool = False,
) -> dict[str, Any]:
    """The exact template context settled in phase0-contracts §5."""
    rendered: list[ArmorSetResult] = []
    for result in page.results:
        if expand_equivalents:
            rendered.extend(expand_equivalent_results(result, resolver))
        else:
            rendered.append(result)
    return {
        "search_id": page.search_id,
        "results": [_result_context(r, resolver) for r in rendered],
        "partial": page.partial,
        "exhausted": page.exhausted,
        "shown_count": page.shown_count,
        "remaining_count": page.remaining_count,
        "advanced_columns": advanced or [],
        "expand_equivalents": expand_equivalents,
    }
