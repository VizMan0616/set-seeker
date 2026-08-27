"""Domain pruning: relevance filter, dominance prune, equivalence collapse.

Pure functions over in-memory pack data (engine-spec.md §1) — a port of the
legacy ``GetRelevantData`` *idea* without its O(n²) list scans. Results are
cached per (pack, query); both are frozen dataclasses and hashable.
"""

from dataclasses import dataclass, replace
from functools import lru_cache

from app.domain.models import Query
from app.engine.data import (
    ARMOR_SLOT_KINDS,
    SLOT_COUNT,
    ArmorPiece,
    Decoration,
    PackData,
    SkillThreshold,
)

_GENDER_CODE = {"m": 0, "f": 1}
_HUNTER_TYPE_CODE = {"blademaster": 0, "gunner": 1}


@dataclass(frozen=True)
class EquivalenceClass:
    representative: ArmorPiece
    members: tuple[ArmorPiece, ...]      # includes the representative, best defense first


@dataclass(frozen=True)
class PrunedPack:
    classes: tuple[tuple[EquivalenceClass, ...], ...]   # per armor slot, len 5
    decorations: tuple[Decoration, ...]
    requested_trees: tuple[int, ...]
    # (tree_id, threshold) for negative skills the search must avoid; empty when
    # the query allows bad skills. Per tree, the threshold closest to zero.
    bad_tree_thresholds: tuple[tuple[int, int], ...]
    skills: tuple[SkillThreshold, ...]   # all pack thresholds, for result reporting
    # Advanced Search: inf = hard + relevance; skyline = dominance rel (Default).
    inf_piece_ids: tuple[tuple[int, ...], ...] = ()
    skyline_piece_ids: tuple[tuple[int, ...], ...] = ()
    inf_decoration_ids: tuple[int, ...] = ()
    skyline_decoration_ids: tuple[int, ...] = ()


def _within_progression_caps(hr_required: int, village_stars: int, query: Query) -> bool:
    """OR-availability: excluded only when BOTH progression paths exceed the caps.

    Legacy semantics (`MHFU-ASS/MH Armor/Armor.cpp:102`): a piece is available
    when reachable via HR *or* via village. The stored values are the per-path
    max(available, required) collapse (ETL column map); 10 is the sentinel for
    "not obtainable via this path" (both caps max at 9). A None cap means that
    path is uncapped, so it always satisfies the OR.
    """
    hr_ok = query.hr is None or hr_required <= query.hr
    village_ok = query.village_stars is None or village_stars <= query.village_stars
    return hr_ok or village_ok


def _passes_hard_filters(piece: ArmorPiece, query: Query) -> bool:
    if piece.gender not in (_GENDER_CODE[query.gender], 2):
        return False
    if piece.hunter_type not in (_HUNTER_TYPE_CODE[query.hunter_type], 2):
        return False
    if not _within_progression_caps(piece.hr_required, piece.village_stars, query):
        return False
    if piece.is_event and not query.allow_event:
        return False
    if piece.torso_inc and not query.allow_torso_inc:
        return False
    return not (piece.is_dummy and not query.allow_dummy)


def hard_filter(pieces: list[ArmorPiece], query: Query) -> list[ArmorPiece]:
    return [p for p in pieces if _passes_hard_filters(p, query)]


def relevance_filter_pieces(
    pieces: list[ArmorPiece], requested: tuple[int, ...]
) -> list[ArmorPiece]:
    """Drop pieces that grant no requested-tree points and have below-max slots.

    A piece with the maximum slot count for its slot is always relevant:
    slots are generic currency (engine-spec.md §1.1).
    """
    trees = set(requested)
    max_slots = [0] * SLOT_COUNT
    for p in pieces:
        max_slots[p.slot] = max(max_slots[p.slot], p.slots)
    return [
        p
        for p in pieces
        if p.slots >= max_slots[p.slot]
        or any(pts != 0 and t in trees for t, pts in p.skills)
    ]


def relevance_filter_decorations(
    decorations: list[Decoration], requested: tuple[int, ...], query: Query
) -> list[Decoration]:
    trees = set(requested)
    return [
        d
        for d in decorations
        if any(pts != 0 and t in trees for t, pts in d.skills)
        and _within_progression_caps(d.hr_required, d.village_stars, query)
        and (query.allow_event or not d.is_event)
    ]


def _solver_subset(
    items: list,
    *,
    skyline: list,
    excluded: set[int],
    forced: set[int],
) -> list:
    """rel = (skyline − excluded) ∪ (forced ∩ inf). Forced wins over exclude."""
    inf_by_id = {item.id: item for item in items}
    rel = [item for item in skyline if item.id not in excluded or item.id in forced]
    seen = {item.id for item in rel}
    for fid in forced:
        if fid in inf_by_id and fid not in seen:
            rel.append(inf_by_id[fid])
            seen.add(fid)
    return rel


def _dominates(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    return all(x >= y for x, y in zip(a, b, strict=True)) and any(
        x > y for x, y in zip(a, b, strict=True)
    )


def _piece_vector(piece: ArmorPiece, requested: tuple[int, ...]) -> tuple[int, ...]:
    skills = dict(piece.skills)
    return (piece.slots, *(skills.get(t, 0) for t in requested))


def dominance_prune(pieces: list[ArmorPiece], requested: tuple[int, ...]) -> list[ArmorPiece]:
    """Skyline pass: drop pieces dominated on (slots, requested-tree points).

    Sorted descending so a piece's dominators are always earlier in the scan;
    the kept list is the running skyline.
    """
    keyed = sorted(
        ((p, _piece_vector(p, requested)) for p in pieces),
        key=lambda pv: pv[1],
        reverse=True,
    )
    kept: list[ArmorPiece] = []
    skyline: list[tuple[int, ...]] = []
    for piece, vec in keyed:
        if not any(_dominates(sv, vec) for sv in skyline):
            kept.append(piece)
            skyline.append(vec)
    return kept


def equivalence_collapse(
    pieces: list[ArmorPiece], requested: tuple[int, ...]
) -> tuple[EquivalenceClass, ...]:
    """Collapse pieces identical on (slots, requested-tree points, torso Inc).

    The representative is the highest-defense member (ties: lowest id); the
    full member list is kept for render-time expansion (engine-spec.md §1.4).
    """
    groups: dict[tuple, list[ArmorPiece]] = {}
    for p in pieces:
        groups.setdefault((p.slots, _piece_vector(p, requested)[1:], p.torso_inc), []).append(p)
    classes = []
    for members in groups.values():
        ordered = tuple(sorted(members, key=lambda p: (-p.defense, p.id)))
        classes.append(EquivalenceClass(representative=ordered[0], members=ordered))
    classes.sort(key=lambda c: c.representative.id)
    return tuple(classes)


@lru_cache(maxsize=128)
def prune(pack: PackData, query: Query) -> PrunedPack:
    """Full pruning pipeline, cached per (pack, query) — engine-spec.md §1."""
    requested = tuple(dict.fromkeys(sr.tree_id for sr in query.skills))
    excluded_p = set(query.excluded_piece_ids)
    forced_p = set(query.forced_piece_ids)
    excluded_d = set(query.excluded_decoration_ids)
    forced_d = set(query.forced_decoration_ids)

    classes_per_slot: list[tuple[EquivalenceClass, ...]] = []
    inf_piece_ids: list[tuple[int, ...]] = []
    skyline_piece_ids: list[tuple[int, ...]] = []
    for slot in range(SLOT_COUNT):
        pieces = [p for p in pack.pieces if p.slot == slot]
        inf = relevance_filter_pieces(hard_filter(pieces, query), requested)
        skyline = dominance_prune(inf, requested)
        inf_piece_ids.append(tuple(sorted(p.id for p in inf)))
        skyline_piece_ids.append(tuple(sorted(p.id for p in skyline)))
        rel = _solver_subset(
            inf, skyline=skyline, excluded=excluded_p, forced=forced_p
        )
        classes_per_slot.append(equivalence_collapse(rel, requested))

    inf_decos = relevance_filter_decorations(list(pack.decorations), requested, query)
    # Jewels have no dominance pass in MHFU; skyline == inf until a pack adds one.
    skyline_decos = inf_decos
    rel_decos = _solver_subset(
        inf_decos, skyline=skyline_decos, excluded=excluded_d, forced=forced_d
    )

    bad: dict[int, int] = {}
    if not query.allow_bad_skills:
        for sk in pack.skills:
            if sk.is_negative:
                bad[sk.tree_id] = max(sk.points, bad.get(sk.tree_id, sk.points))

    return PrunedPack(
        classes=tuple(classes_per_slot),
        decorations=tuple(rel_decos),
        requested_trees=requested,
        bad_tree_thresholds=tuple(sorted(bad.items())),
        skills=pack.skills,
        inf_piece_ids=tuple(inf_piece_ids),
        skyline_piece_ids=tuple(skyline_piece_ids),
        inf_decoration_ids=tuple(sorted(d.id for d in inf_decos)),
        skyline_decoration_ids=tuple(sorted(d.id for d in skyline_decos)),
    )


def domain_snapshot(pack: PackData, pruned: PrunedPack) -> dict:
    """Pack-standard Advanced Search snapshot, keyed by slot kind (ADR 0001)."""
    kinds: dict[str, dict[str, list[int]]] = {}
    for index, kind in enumerate(ARMOR_SLOT_KINDS):
        kinds[kind] = {
            "inf_ids": list(pruned.inf_piece_ids[index]),
            "rel_ids": list(pruned.skyline_piece_ids[index]),
        }
    kinds["decorations"] = {
        "inf_ids": list(pruned.inf_decoration_ids),
        "rel_ids": list(pruned.skyline_decoration_ids),
    }
    if pack.talismans:
        kinds["charms"] = {"inf_ids": [], "rel_ids": []}
    if pack.weapon_search:
        kinds["weapons"] = {"inf_ids": [], "rel_ids": []}
    return {"kinds": kinds}


def apply_rel_checks(
    query: Query,
    pack: PackData,
    checked_piece_ids: tuple[int, ...],
    checked_decoration_ids: tuple[int, ...],
) -> Query:
    """Map Advanced checks onto excluded_* / forced_* against current inf/skyline."""
    base = replace(
        query,
        excluded_piece_ids=(),
        excluded_decoration_ids=(),
        forced_piece_ids=(),
        forced_decoration_ids=(),
    )
    pruned = prune(pack, base)
    inf_p = {pid for slot in pruned.inf_piece_ids for pid in slot}
    sky_p = {pid for slot in pruned.skyline_piece_ids for pid in slot}
    inf_d = set(pruned.inf_decoration_ids)
    sky_d = set(pruned.skyline_decoration_ids)
    checked_p = set(checked_piece_ids) & inf_p
    checked_d = set(checked_decoration_ids) & inf_d
    return replace(
        query,
        excluded_piece_ids=tuple(sorted(inf_p - checked_p)),
        excluded_decoration_ids=tuple(sorted(inf_d - checked_d)),
        forced_piece_ids=tuple(sorted(checked_p - sky_p)),
        forced_decoration_ids=tuple(sorted(checked_d - sky_d)),
    )
