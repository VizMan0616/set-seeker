# ADR 0011: Penalty neutralization before spare slots

- Status: accepted
- Date: 2026-08-29
- Extends: [ADR 0005](0005-iterate-and-exclude-enumeration.md)

## Context

ADR 0005 ranks each iterate-and-exclude solve as weakest required charm → spare
slots → defense. Armor pieces often carry negative skill-tree points. Without
decorations that grant those trees in the pruned domain, `points[t] ≥
neg_threshold + 1` is unsatisfiable whenever every legal set sits on a penalty
tree — so the engine either drops those sets or, when the query allows bad
skills, prefers leftover sockets over spending a socket to turn the penalty off.

That order is generation-agnostic: any pack whose skill table has `is_negative`
rows can neutralize with jewels. It must not depend on a game id or on a named
tree (Health, Vitality, …).

## Decision

Keep iterate-and-exclude. Insert one lexicographic tier between charm strength
and spare sockets:

1. Minimize required charm strength
2. **Minimize the number of active penalty skills** (trees at or below their
   closest-to-zero negative threshold)
3. Maximize spare slots
4. Maximize defense
5. Query sort tie-breakers

When `allow_bad_skills` is off, the existing floor `points[t] ≥ neg_threshold + 1`
stays a hard constraint (now reachable because fixer decorations enter the
domain). When it is on, the floor is dropped and the new tier prefers fewer
active penalties before leftover sockets.

The decoration relevance filter admits jewels that point at a negative-threshold
tree **and** that tree already has nonzero points on pruned pieces or charms.
No pack flag.

## Consequences

- Weighted-sum bounds in the CP-SAT objective grow by one exact tier
  (`penalty_weight` above spare, below charm).
- Result `active_skills` reports remaining negative threshold rows so the card
  can show leftover penalties.
- Enumeration and exclusion tuples are unchanged.
