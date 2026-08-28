"""Legal charm domain for packs with ``talismans: true``.

Generated candidates come from pack charm-type envelopes (data-pack-spec.md),
not per-game branches. Charm-table RNG simulation is out of scope until a pack
stores per-table maxima (MH3U-style ``mh3u_charm_tables``).
"""

from itertools import combinations

from app.domain.models import NONE_CHARM_ID, CharmSpec, Query
from app.engine.data import PackData


def charm_strength(slots: int, skills: tuple[tuple[int, int], ...]) -> int:
    """Weaker legal charms score lower (engine-spec.md §3 objective 1)."""
    if not skills and slots == 0:
        return 0
    pts = [abs(p) for _, p in skills]
    while len(pts) < 2:
        pts.append(0)
    return len(skills) * 10_000 + pts[0] * 100 + pts[1] * 10 + slots


def charm_candidates(pack: PackData, query: Query) -> tuple[CharmSpec, ...]:
    """none ∪ inventory ∪ query-relevant generated envelopes, then Advanced filters."""
    none = CharmSpec(id=NONE_CHARM_ID, slots=0, skills=())
    if not pack.talismans:
        return (none,)

    unique: dict[tuple[int, tuple[tuple[int, int], ...]], CharmSpec] = {}

    def consider(spec: CharmSpec) -> None:
        key = (spec.slots, spec.skills)
        prev = unique.get(key)
        if prev is None or (spec.id > 0 and prev.id <= 0):
            unique[key] = spec
        elif spec.id > 0 and prev.id > 0 and spec.id < prev.id:
            unique[key] = spec

    for charm in query.user_charms:
        consider(CharmSpec(id=charm.id, slots=charm.slots, skills=charm.skills))

    if query.use_generated_charms:
        requested = tuple(dict.fromkeys(sr.tree_id for sr in query.skills))
        for kind in pack.charm_types:
            _generate_type(kind, requested, consider)

    ordered = sorted(unique.values(), key=lambda c: (c.slots, c.skills, -c.id))
    generated_id = -1
    assigned: list[CharmSpec] = [none]
    for spec in ordered:
        if spec.id > 0:
            assigned.append(spec)
            continue
        assigned.append(CharmSpec(id=generated_id, slots=spec.slots, skills=spec.skills))
        generated_id -= 1

    excluded = set(query.excluded_charm_ids)
    forced = set(query.forced_charm_ids)
    kept = [
        c
        for c in assigned
        if c.id == NONE_CHARM_ID or c.id in forced or c.id not in excluded
    ]
    if not any(c.id == NONE_CHARM_ID for c in kept):
        kept.insert(0, none)
    return tuple(kept)


def _fulfillment(weighted: tuple[tuple[int, int], ...]) -> int:
    """Rank points from skill values vs envelope maxima (MHP3 getRankPoint)."""
    px = 0.0
    for pts, hi in weighted:
        if hi <= 0:
            continue
        px += pts / (hi / 10.0)
    return int(px)


def _slot_cap(kind, weighted: tuple[tuple[int, int], ...]) -> int:
    type_cap = max(0, min(3, kind.max_slots))
    if not kind.slot_thresholds:
        return type_cap
    rank = _fulfillment(weighted)
    by_rank = {fulfillment: slots for fulfillment, slots in kind.slot_thresholds}
    if rank in by_rank:
        allowed = by_rank[rank]
    else:
        keys = sorted(by_rank)
        if not keys:
            return type_cap
        if rank < keys[0]:
            allowed = by_rank[keys[0]]
        else:
            allowed = by_rank[max(k for k in keys if k <= rank)]
    return max(0, min(type_cap, allowed))


def _emit_slots(consider, skills: tuple[tuple[int, int], ...], cap: int) -> None:
    for slots in range(0, cap + 1):
        if not skills and slots == 0:
            continue
        consider(CharmSpec(id=-1, slots=slots, skills=skills))


def _generate_type(kind, requested: tuple[int, ...], consider) -> None:
    skill1 = {tree: (lo, hi) for tree, lo, hi in kind.skill1}
    skill2 = {tree: (lo, hi) for tree, lo, hi in kind.skill2}
    one_skill = {**skill2, **skill1}

    _emit_slots(consider, (), _slot_cap(kind, ()))

    for tree in requested:
        rng = one_skill.get(tree)
        if rng is None:
            continue
        lo, hi = rng
        for pts in range(max(lo, 1), hi + 1):
            skills = ((tree, pts),)
            _emit_slots(consider, skills, _slot_cap(kind, ((pts, hi),)))

    if not skill2 or len(requested) < 2:
        return
    for t1, t2 in combinations(requested, 2):
        for tree_a, tree_b, map_a, map_b in (
            (t1, t2, skill1, skill2),
            (t2, t1, skill1, skill2),
        ):
            rng_a, rng_b = map_a.get(tree_a), map_b.get(tree_b)
            if rng_a is None or rng_b is None:
                continue
            lo_a, hi_a = rng_a
            lo_b, hi_b = rng_b
            for pts_a in range(max(lo_a, 1), hi_a + 1):
                for pts_b in range(max(lo_b, 1), hi_b + 1):
                    skills = ((tree_a, pts_a), (tree_b, pts_b))
                    cap = _slot_cap(kind, ((pts_a, hi_a), (pts_b, hi_b)))
                    _emit_slots(consider, skills, cap)
