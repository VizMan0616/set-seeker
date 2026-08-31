"""CP-SAT model build + solve (engine-spec.md §2, §3, §5).

One index variable per armor slot over the pruned equivalence-class
representatives, decoration count/placement variables with per-piece slot
capacity, skill thresholds, and the no-bad-skills constraint. Each call
solves for exactly one ranked set; enumeration lives in service.py as
iterate-and-exclude (ADR 0005). Charm variable is present when pack flag ``talismans`` is true
(inventory ∪ generated legal envelopes ∪ none).

Objective order (ADR 0005 as extended by ADR 0011):
1. minimize required charm strength — constant 0 when there is only none;
2. minimize active penalty skills (trees at or below their negative threshold);
3. maximize spare slots; 4. maximize defense; 5. query sort tie-breakers.
Implemented as a single weighted sum with bounds derived from the pruned
data so the lexicographic order is exact.
"""

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.domain.models import (
    NONE_CHARM_ID,
    ArmorSetResult,
    CharmSpec,
    DecorationAssignment,
    Query,
)
from app.engine.charms import charm_strength
from app.engine.data import BODY, SLOT_COUNT, PackData
from app.engine.pruning import PrunedPack

WEAPON_BUCKET = SLOT_COUNT  # decoration placement bucket index for the weapon
CHARM_BUCKET = SLOT_COUNT + 1

_RES_ATTR = {
    "res_fire": "res_fire",
    "res_water": "res_water",
    "res_ice": "res_ice",
    "res_thunder": "res_thunder",
    "res_dragon": "res_dragon",
}


@dataclass(frozen=True)
class SolveOutcome:
    # optimal | feasible (ranked, budget) | unranked (feasibility-first) |
    # infeasible | unknown (budget, no assignment)
    status: str
    result: ArmorSetResult | None


def solve_one(
    *,
    pack: PackData,
    pruned: PrunedPack,
    query: Query,
    exclusions: list[tuple[int, ...]],
    time_limit_ms: int,
    num_workers: int = 1,
    rank: bool = True,
) -> SolveOutcome:
    """Solve for one set not in ``exclusions``.

    With ``rank=True`` (default), maximize weakest-charm → fewer penalties →
    slots → defense.
    With ``rank=False``, stop at the first feasible assignment so a large
    charm table can still return *a* set inside the time budget.

    ``num_workers`` defaults to 1 so results are deterministic; on this data
    size each solve is milliseconds (engine-spec.md §4).
    """
    if any(len(classes) == 0 for classes in pruned.classes):
        return SolveOutcome("infeasible", None)

    model = cp_model.CpModel()

    # Requested trees plus penalty trees that can move on this domain.
    # Other activated skills are computed in `_extract` from the assignment.
    live: set[int] = set()
    for classes in pruned.classes:
        for cls in classes:
            for tree_id, pts in cls.representative.skills:
                if pts < 0:
                    live.add(tree_id)
    for spec in pruned.charms or ():
        for tree_id, pts in spec.skills:
            if pts < 0:
                live.add(tree_id)
    modeled_bad = tuple(
        (tree_id, threshold)
        for tree_id, threshold in pruned.bad_tree_thresholds
        if tree_id in live
    )
    # allow_bad off: hard floors + fixer jewels only for penalties reachable on
    # armor/charms (modeled_bad). allow_bad on: reified penalty tier for every
    # negative threshold (ADR 0011), still far fewer trees than the full table.
    if query.allow_bad_skills:
        penalty_thresholds = pruned.bad_tree_thresholds
        trees = tuple(
            dict.fromkeys(
                [*pruned.requested_trees, *[t for t, _ in pruned.bad_tree_thresholds]]
            )
        )
    else:
        penalty_thresholds = modeled_bad
        trees = tuple(
            dict.fromkeys([*pruned.requested_trees, *[t for t, _ in modeled_bad]])
        )

    # --- one index variable per slot over equivalence-class representatives ---
    x = [
        model.new_int_var(0, len(classes) - 1, f"piece_{s}")
        for s, classes in enumerate(pruned.classes)
    ]
    reps = [[c.representative for c in classes] for classes in pruned.classes]

    def element_of(index: cp_model.IntVar, vals: list[int], name: str) -> cp_model.IntVar:
        v = model.new_int_var(min(vals), max(vals), name)
        model.add_element(index, vals, v)
        return v

    def element(s: int, vals: list[int], name: str) -> cp_model.IntVar:
        return element_of(x[s], vals, name)

    slots_var = [element(s, [r.slots for r in reps[s]], f"slots_{s}") for s in range(SLOT_COUNT)]
    defense_var = [
        element(s, [r.defense for r in reps[s]], f"defense_{s}") for s in range(SLOT_COUNT)
    ]
    piece_pts = {
        (s, t): element(
            s, [dict(r.skills).get(t, 0) for r in reps[s]], f"pts_{s}_{t}"
        )
        for s in range(SLOT_COUNT)
        for t in trees
    }
    # Athena adds ``torso_inc`` from every piece (head/arms/waist/legs first),
    # then applies the multiplier to the body. One flag still means ×2.
    torso_flags = [
        element(s, [1 if r.torso_inc else 0 for r in reps[s]], f"ti_flag_{s}")
        for s in range(SLOT_COUNT)
    ]
    torso_inc = model.new_int_var(0, 1, "torso_inc")
    model.add_max_equality(torso_inc, torso_flags)

    charms = pruned.charms or ()
    if not charms:
        charms = (CharmSpec(id=NONE_CHARM_ID),)
    charm_x = model.new_int_var(0, len(charms) - 1, "charm")
    charm_slots_var = element_of(charm_x, [c.slots for c in charms], "charm_slots")
    charm_strength_var = element_of(
        charm_x, [charm_strength(c.slots, c.skills) for c in charms], "charm_strength"
    )
    charm_pts = {
        t: element_of(
            charm_x, [dict(c.skills).get(t, 0) for c in charms], f"charm_pts_{t}"
        )
        for t in trees
    }

    # --- decoration counts and per-bucket placement ---
    # A jewel of size k occupies k sockets on a single piece (or the weapon);
    # per-piece capacity makes "smaller jewel fits larger slot" unnecessary to
    # model explicitly — sockets are generic.
    decos = pruned.decorations
    deco_skills = {d.id: dict(d.skills) for d in decos}
    max_sockets = 3 * SLOT_COUNT + 6
    deco_count: dict[int, cp_model.IntVar] = {}
    place: dict[tuple[int, int], cp_model.IntVar] = {}
    for d in decos:
        count = model.new_int_var(0, max_sockets // d.size, f"deco_count_{d.id}")
        deco_count[d.id] = count
        bucket_vars = []
        for b in range(SLOT_COUNT + 2):
            pv = model.new_int_var(0, 3, f"place_{d.id}_{b}")
            place[d.id, b] = pv
            bucket_vars.append(pv)
        model.add(count == sum(bucket_vars))

    for s in range(SLOT_COUNT):
        model.add(sum(d.size * place[d.id, s] for d in decos) <= slots_var[s])
    model.add(
        sum(d.size * place[d.id, WEAPON_BUCKET] for d in decos) <= query.weapon_slots
    )
    model.add(
        sum(d.size * place[d.id, CHARM_BUCKET] for d in decos) <= charm_slots_var
    )

    # --- points per tracked tree (body piece and body-socketed jewels doubled
    # under Torso Inc) ---
    max_piece = max(
        (abs(v) for s in range(SLOT_COUNT) for r in reps[s] for v in dict(r.skills).values()),
        default=0,
    )
    max_deco = max(
        (abs(v) for d in decos for v in deco_skills[d.id].values()), default=0
    )
    max_charm = max(
        (abs(p) for c in charms for _, p in c.skills),
        default=0,
    )
    bound = 2 * SLOT_COUNT * max_piece + 2 * max_sockets * max_deco + max_charm + 1

    points: dict[int, cp_model.IntVar] = {}
    for t in trees:
        terms: list = []
        for s in range(SLOT_COUNT):
            if s == BODY:
                extra = model.new_int_var(-bound, bound, f"ti_body_{t}")
                model.add_multiplication_equality(extra, [piece_pts[s, t], torso_inc])
                terms.append(piece_pts[s, t] + extra)
            else:
                terms.append(piece_pts[s, t])
        for b in range(SLOT_COUNT + 2):
            expr = sum(deco_skills[d.id].get(t, 0) * place[d.id, b] for d in decos)
            if isinstance(expr, int):
                continue  # no decoration grants this tree
            if b == BODY:
                extra = model.new_int_var(-bound, bound, f"ti_deco_{t}")
                model.add_multiplication_equality(extra, [expr, torso_inc])
                terms.append(expr + extra)
            else:
                terms.append(expr)
        terms.append(charm_pts[t])
        total = model.new_int_var(-bound, bound, f"points_{t}")
        model.add(total == sum(terms))
        points[t] = total

    # --- hard constraints ---
    for sr in query.skills:
        model.add(points[sr.tree_id] >= sr.min_points)
    penalty_terms: list = []
    for t, neg_threshold in penalty_thresholds:
        if not query.allow_bad_skills:
            model.add(points[t] >= neg_threshold + 1)
        else:
            active = model.new_bool_var(f"penalty_{t}")
            model.add(points[t] <= neg_threshold).only_enforce_if(active)
            model.add(points[t] >= neg_threshold + 1).only_enforce_if(~active)
            penalty_terms.append(active)

    # --- exclusions (iterate-and-exclude, ADR 0005): representative id tuples ---
    id_to_idx = [
        {r.id: i for i, r in enumerate(reps[s])} for s in range(SLOT_COUNT)
    ]
    charm_id_to_idx = {c.id: i for i, c in enumerate(charms)}
    for n, excl in enumerate(exclusions):
        padded = tuple(excl) + (NONE_CHARM_ID,) if len(excl) == SLOT_COUNT else tuple(excl)
        lits = []
        for s in range(SLOT_COUNT):
            idx = id_to_idx[s].get(padded[s])
            if idx is None:
                break  # stale exclusion against a re-pruned domain; cannot recur
            lit = model.new_bool_var(f"excl_{n}_{s}")
            model.add(x[s] != idx).only_enforce_if(lit)
            lits.append(lit)
        else:
            if len(padded) > SLOT_COUNT:
                cidx = charm_id_to_idx.get(padded[SLOT_COUNT])
                if cidx is None:
                    continue
                lit = model.new_bool_var(f"excl_{n}_charm")
                model.add(charm_x != cidx).only_enforce_if(lit)
                lits.append(lit)
            model.add_bool_or(lits)

    # --- lexicographic objective as one weighted sum ---
    sockets_total = sum(slots_var) + query.weapon_slots + charm_slots_var
    sockets_used = sum(d.size * deco_count[d.id] for d in decos)
    spare = sockets_total - sockets_used
    defense = sum(defense_var)

    max_defense = sum(max(r.defense for r in reps[s]) for s in range(SLOT_COUNT))
    if query.sort == "rarity":
        rarity_var = [
            element(s, [r.rarity for r in reps[s]], f"rarity_{s}") for s in range(SLOT_COUNT)
        ]
        tie = -sum(rarity_var)  # lower rarity is easier to obtain
        tie_bound = sum(max(r.rarity for r in reps[s]) for s in range(SLOT_COUNT)) + 1
    elif query.sort in _RES_ATTR:
        attr = _RES_ATTR[query.sort]
        res_var = [
            element(s, [getattr(r, attr) for r in reps[s]], f"res_{s}")
            for s in range(SLOT_COUNT)
        ]
        tie = sum(res_var)
        tie_bound = (
            sum(max(abs(getattr(r, attr)) for r in reps[s]) for s in range(SLOT_COUNT)) + 1
        )
    else:  # "defense" / "slots" are already objective tiers
        tie = 0
        tie_bound = 1

    max_spare = 3 * SLOT_COUNT + 6
    n_bad = len(penalty_thresholds)
    mid_weight = (max_defense + 1) * tie_bound
    penalty_weight = (max_spare + 1) * mid_weight
    charm_weight = (n_bad + 1) * penalty_weight
    max_str = max(charm_strength(c.slots, c.skills) for c in charms)
    weak_charm = max_str - charm_strength_var
    fewer_penalties = n_bad - (sum(penalty_terms) if penalty_terms else 0)
    if rank:
        model.maximize(
            weak_charm * charm_weight
            + fewer_penalties * penalty_weight
            + spare * mid_weight
            + defense * tie_bound
            + tie
        )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_ms / 1000.0
    if not rank:
        solver.parameters.stop_after_first_solution = True
    try:
        solver.parameters.num_workers = num_workers
    except AttributeError:
        solver.parameters.num_search_workers = num_workers

    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        return SolveOutcome("infeasible", None)
    if status == cp_model.MODEL_INVALID:
        raise ValueError("CP-SAT model invalid — engine bug, not a query result")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveOutcome("unknown", None)

    result = _extract(
        solver, pruned, query, x, deco_count, place, points, decos, charms, charm_x
    )
    if not rank:
        return SolveOutcome("unranked", result)
    return SolveOutcome("optimal" if status == cp_model.OPTIMAL else "feasible", result)


def _assignment_points(chosen, chosen_charm, query, decos, place, solver) -> dict[int, int]:
    """Skill totals from the chosen pieces/jewels — covers trees not in the model."""
    torso = any(cls.representative.torso_inc for cls in chosen)
    totals: dict[int, int] = {}

    def add(tree_id: int, pts: int, *, body: bool = False) -> None:
        if pts == 0:
            return
        totals[tree_id] = totals.get(tree_id, 0) + (pts * (2 if body and torso else 1))

    for slot, cls in enumerate(chosen):
        for tree_id, pts in cls.representative.skills:
            add(tree_id, pts, body=slot == BODY)
    for tree_id, pts in chosen_charm.skills:
        add(tree_id, pts)
    for deco in decos:
        for bucket in range(SLOT_COUNT + 2):
            count = solver.value(place[deco.id, bucket])
            if count <= 0:
                continue
            for tree_id, pts in deco.skills:
                add(tree_id, pts * count, body=bucket == BODY)
    return totals


def _extract(
    solver: cp_model.CpSolver,
    pruned: PrunedPack,
    query: Query,
    x: list[cp_model.IntVar],
    deco_count: dict[int, cp_model.IntVar],
    place: dict[tuple[int, int], cp_model.IntVar],
    points: dict[int, cp_model.IntVar],
    decos,
    charms,
    charm_x: cp_model.IntVar,
) -> ArmorSetResult:
    chosen = [pruned.classes[s][solver.value(x[s])] for s in range(SLOT_COUNT)]

    decorations = tuple(
        DecorationAssignment(decoration_id=d.id, count=solver.value(deco_count[d.id]))
        for d in sorted(decos, key=lambda d: d.id)
        if solver.value(deco_count[d.id]) > 0
    )

    # Spare sockets per bucket, grouped by the largest jewel size they fit.
    spare = [0, 0, 0]
    leftover = []
    chosen_charm = charms[solver.value(charm_x)]
    for b in range(SLOT_COUNT + 2):
        if b < SLOT_COUNT:
            cap = chosen[b].representative.slots
        elif b == WEAPON_BUCKET:
            cap = query.weapon_slots
        else:
            cap = chosen_charm.slots
        used = sum(solver.value(place[d.id, b]) * d.size for d in decos)
        remaining = cap - used
        leftover.append(remaining)
        if 1 <= remaining <= 3:
            spare[remaining - 1] += 1

    achieved = _assignment_points(
        chosen, chosen_charm, query, decos, place, solver
    )
    achieved.update({t: solver.value(v) for t, v in points.items()})
    thresholds_by_tree: dict[int, list] = {}
    for sk in pruned.skills:
        thresholds_by_tree.setdefault(sk.tree_id, []).append(sk)
    active = []
    for t in sorted(thresholds_by_tree):
        pts = achieved.get(t, 0)
        pos = [sk for sk in thresholds_by_tree[t] if not sk.is_negative]
        neg = [sk for sk in thresholds_by_tree[t] if sk.is_negative]
        if pos:
            crossed = [sk for sk in pos if pts >= sk.points]
            if crossed:
                best = max(crossed, key=lambda sk: sk.points)
                active.append((best.id, pts))
        if neg:
            crossed = [sk for sk in neg if pts <= sk.points]
            if crossed:
                worst = min(crossed, key=lambda sk: sk.points)
                active.append((worst.id, pts))

    return ArmorSetResult(
        piece_ids=tuple(c.representative.id for c in chosen),
        alternates=tuple(tuple(m.id for m in c.members) for c in chosen),
        decorations=decorations,
        charm_id=None if chosen_charm.id == NONE_CHARM_ID else chosen_charm.id,
        active_skills=tuple(active),
        spare_slots=tuple(spare),
        defense=sum(c.representative.defense for c in chosen),
        charm_slots=chosen_charm.slots,
        charm_skills=chosen_charm.skills,
        spare_by_piece=tuple(leftover),
        weapon_slots=query.weapon_slots,
    )
