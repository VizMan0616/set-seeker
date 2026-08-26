"""CP-SAT model build + solve (engine-spec.md §2, §3, §5).

One index variable per armor slot over the pruned equivalence-class
representatives, decoration count/placement variables with per-piece slot
capacity, skill thresholds, and the no-bad-skills constraint. Each call
solves for exactly one ranked set; enumeration lives in service.py as
iterate-and-exclude (ADR 0005). No charm variable for MHFU
(pack flag ``talismans: false``).

Objective order (settled; changing it requires superseding ADR 0005):
1. minimize required charm strength — trivially none for MHFU, no term;
2. maximize spare slots; 3. maximize defense; 4. query sort tie-breakers.
Implemented as a single weighted sum with bounds derived from the pruned
data so the lexicographic order is exact.
"""

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.domain.models import ArmorSetResult, DecorationAssignment, Query
from app.engine.data import BODY, SLOT_COUNT, PackData
from app.engine.pruning import PrunedPack

WEAPON_BUCKET = SLOT_COUNT  # decoration placement bucket index for the weapon

_RES_ATTR = {
    "res_fire": "res_fire",
    "res_water": "res_water",
    "res_ice": "res_ice",
    "res_thunder": "res_thunder",
    "res_dragon": "res_dragon",
}


@dataclass(frozen=True)
class SolveOutcome:
    status: str  # "optimal" | "feasible" (budget hit) | "infeasible" | "unknown" (budget hit)
    result: ArmorSetResult | None


def solve_one(
    *,
    pack: PackData,
    pruned: PrunedPack,
    query: Query,
    exclusions: list[tuple[int, int, int, int, int]],
    time_limit_ms: int,
    num_workers: int = 1,
) -> SolveOutcome:
    """Solve for the single best set not in ``exclusions``.

    ``num_workers`` defaults to 1 so results are deterministic; on this data
    size each solve is milliseconds (engine-spec.md §4).
    """
    if any(len(classes) == 0 for classes in pruned.classes):
        return SolveOutcome("infeasible", None)

    model = cp_model.CpModel()

    # Track every tree the model must reason about: requested trees, bad-skill
    # trees, and any tree with a defined threshold (for active_skills reporting).
    trees = tuple(
        dict.fromkeys(
            [*pruned.requested_trees]
            + [t for t, _ in pruned.bad_tree_thresholds]
            + [sk.tree_id for sk in pruned.skills]
        )
    )

    # --- one index variable per slot over equivalence-class representatives ---
    x = [
        model.new_int_var(0, len(classes) - 1, f"piece_{s}")
        for s, classes in enumerate(pruned.classes)
    ]
    reps = [[c.representative for c in classes] for classes in pruned.classes]

    def element(s: int, vals: list[int], name: str) -> cp_model.IntVar:
        v = model.new_int_var(min(vals), max(vals), name)
        model.add_element(x[s], vals, v)
        return v

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
    torso_inc = element(
        BODY, [1 if r.torso_inc else 0 for r in reps[BODY]], "torso_inc"
    )

    # --- decoration counts and per-bucket placement ---
    # A jewel of size k occupies k sockets on a single piece (or the weapon);
    # per-piece capacity makes "smaller jewel fits larger slot" unnecessary to
    # model explicitly — sockets are generic.
    decos = pruned.decorations
    deco_skills = {d.id: dict(d.skills) for d in decos}
    max_sockets = 3 * SLOT_COUNT + 3
    deco_count: dict[int, cp_model.IntVar] = {}
    place: dict[tuple[int, int], cp_model.IntVar] = {}
    for d in decos:
        count = model.new_int_var(0, max_sockets // d.size, f"deco_count_{d.id}")
        deco_count[d.id] = count
        bucket_vars = []
        for b in range(SLOT_COUNT + 1):
            pv = model.new_int_var(0, 3, f"place_{d.id}_{b}")
            place[d.id, b] = pv
            bucket_vars.append(pv)
        model.add(count == sum(bucket_vars))

    for s in range(SLOT_COUNT):
        model.add(sum(d.size * place[d.id, s] for d in decos) <= slots_var[s])
    model.add(
        sum(d.size * place[d.id, WEAPON_BUCKET] for d in decos) <= query.weapon_slots
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
    bound = 2 * SLOT_COUNT * max_piece + 2 * max_sockets * max_deco + 1

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
        for b in range(SLOT_COUNT + 1):
            expr = sum(deco_skills[d.id].get(t, 0) * place[d.id, b] for d in decos)
            if isinstance(expr, int):
                continue  # no decoration grants this tree
            if b == BODY:
                extra = model.new_int_var(-bound, bound, f"ti_deco_{t}")
                model.add_multiplication_equality(extra, [expr, torso_inc])
                terms.append(expr + extra)
            else:
                terms.append(expr)
        total = model.new_int_var(-bound, bound, f"points_{t}")
        model.add(total == sum(terms))
        points[t] = total

    # --- hard constraints ---
    for sr in query.skills:
        model.add(points[sr.tree_id] >= sr.min_points)
    for t, neg_threshold in pruned.bad_tree_thresholds:
        model.add(points[t] >= neg_threshold + 1)

    # --- exclusions (iterate-and-exclude, ADR 0005): representative id tuples ---
    id_to_idx = [
        {r.id: i for i, r in enumerate(reps[s])} for s in range(SLOT_COUNT)
    ]
    for n, excl in enumerate(exclusions):
        lits = []
        for s in range(SLOT_COUNT):
            idx = id_to_idx[s].get(excl[s])
            if idx is None:
                break  # stale exclusion against a re-pruned domain; cannot recur
            lit = model.new_bool_var(f"excl_{n}_{s}")
            model.add(x[s] != idx).only_enforce_if(lit)
            lits.append(lit)
        else:
            model.add_bool_or(lits)

    # --- lexicographic objective as one weighted sum ---
    sockets_total = sum(slots_var) + query.weapon_slots
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

    model.maximize(spare * (max_defense + 1) * tie_bound + defense * tie_bound + tie)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_ms / 1000.0
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

    result = _extract(solver, pruned, query, x, deco_count, place, points, decos)
    return SolveOutcome("optimal" if status == cp_model.OPTIMAL else "feasible", result)


def _extract(
    solver: cp_model.CpSolver,
    pruned: PrunedPack,
    query: Query,
    x: list[cp_model.IntVar],
    deco_count: dict[int, cp_model.IntVar],
    place: dict[tuple[int, int], cp_model.IntVar],
    points: dict[int, cp_model.IntVar],
    decos,
) -> ArmorSetResult:
    chosen = [pruned.classes[s][solver.value(x[s])] for s in range(SLOT_COUNT)]

    decorations = tuple(
        DecorationAssignment(decoration_id=d.id, count=solver.value(deco_count[d.id]))
        for d in sorted(decos, key=lambda d: d.id)
        if solver.value(deco_count[d.id]) > 0
    )

    # Spare sockets per bucket, grouped by the largest jewel size they fit.
    spare = [0, 0, 0]
    for b in range(SLOT_COUNT + 1):
        cap = chosen[b].representative.slots if b < SLOT_COUNT else query.weapon_slots
        used = sum(solver.value(place[d.id, b]) * d.size for d in decos)
        remaining = cap - used
        if 1 <= remaining <= 3:
            spare[remaining - 1] += 1

    achieved = {t: solver.value(v) for t, v in points.items()}
    thresholds_by_tree: dict[int, list] = {}
    for sk in pruned.skills:
        if not sk.is_negative:
            thresholds_by_tree.setdefault(sk.tree_id, []).append(sk)
    active = []
    for t in sorted(thresholds_by_tree):
        crossed = [sk for sk in thresholds_by_tree[t] if achieved.get(t, 0) >= sk.points]
        if crossed:
            best = max(crossed, key=lambda sk: sk.points)
            active.append((best.id, achieved[t]))

    return ArmorSetResult(
        piece_ids=tuple(c.representative.id for c in chosen),
        alternates=tuple(tuple(m.id for m in c.members) for c in chosen),
        decorations=decorations,
        charm_id=None,  # mhfu: pack flag talismans is false
        active_skills=tuple(active),
        spare_slots=tuple(spare),
        defense=sum(c.representative.defense for c in chosen),
    )
