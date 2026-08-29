# Generated-charm domain vs the 2 s solve budget

Replay this when optimizing the CP-SAT charm variable. Do **not** “fix” it by
raising the wall-clock limit or by copying Athena’s per-charm worker fan-out
(`docs/legacy-analysis/overview.md`, ADR 0002 / 0005).

## Symptom

UI: *No sets activate those skills…* plus *Search hit its time budget — more
sets may exist than shown.* (`partial` from `solve_one` status `unknown` /
budget-feasible with no proven first set).

Default budget: `SOLVER_TIME_LIMIT_MS = 2000` (`app/config.py`).

**Use my charms** (default off) = session inventory only. Unchecked = pack
charm tables (`use_generated_charms`). Checking inventory after a generated
timeout used to look like the owned charm was “cached as legal” — that was
stale Advanced Search `rel_charm_id` checkboxes, not a change in legality.

## Repro (MHP3, TMO names, 2026-08)

Owned charm: **Water Atk +5, Attack +9, 0 slots** (Dragon / timeworn-shaped).
Weapon slots: 0. Gender: female. Hunter: blademaster. Ranks: 6/6 or uncapped.

Desired skills (thresholds are the *activated skill* rows, not raw tree +N):

| Skill (TMO) | Tree | Points required |
|---|---|---|
| Water Atk +2 | Water Atk | 15 |
| Attack Up (M) | Attack | 15 |
| Spirit's Whim | Whim | 10 |
| Recovery Up | Rec Level | 10 |
| Divine Blessing | Protection | 10 |
| Speed Sharpening | Sharpener | 10 |

This set exists in-game. Inventory-only search finds it. Generated-on with a
**full** two-skill point grid did not finish in 2 s.

The charm **is** inside the pack envelopes (timeworn skill 1 Water Atk ≤ 7,
skill 2 Attack ≤ 10). Advanced Search listed `Water Atk +5, Attack +9 ---`
among thousands of generated rows when generated was on.

## Why it dies

`charm` is one `IntVar` over a table (`app/engine/solver.py`). Each generated
`CharmSpec` is a row: Element-of lookups for slots, strength, and per-tree
points.

`_generate_type` (`app/engine/charms.py`) used to emit **every** legal
`(pts1 × pts2 × slots)` for every ordered pair of **requested** trees and every
charm type (mystery / shining / timeworn). Six requested trees → C(6,2)×2
orders × ~7×10 points × 0–3 slots × two two-skill types ≈ **thousands of
rows**. CP-SAT hits `max_time_in_seconds` before a feasible assignment.

This is **not** Athena’s `GenerateCharmTable` / 12-table RNG. We expanded
envelopes into an explicit domain. Athena fans out workers per charm template
(do not copy that).

## Mitigations already in tree (palliative)

1. **Inventory first** — `_solve_page` (`app/engine/service.py`): if the session
   has `user_charms` and generated is on, solve `use_generated_charms=False`
   first. Page 1 of this repro should return the owned charm.
2. **Two-skill corners only** — `_corner_pts`: min/max (and skill-2 floor if
   negative), not every integer. One-skill still uses the full positive range
   (small).
3. **Find sets clears Advanced** — so leftover `rel_charm_id` does not exclude
   generated charms on the next run.
4. Advanced snapshot after an inventory-first page lists **inventory**, not the
   full generated catalog.
5. **Feasibility-first + scroll pages** — if a ranked `solve_one` returns
   `unknown` on a generated-charm query, the same 2 s budget retries without
   maximize (`stop_after_first_solution`). The UI then pages on scroll (one
   prefetched `PAGE_SIZE` lookahead, hard stop at 1000 *shown cards*). This
   does not replace a structured `charm_x` model; it avoids an empty first
   paint when any legal set exists inside the budget.

Generated-only (empty My talismans) on this 70-point query can still miss the
budget if even the unranked attempt stays `UNKNOWN`. Corners also omit mid-envelope rolls (e.g. +5/+9) from the generated
*list* even though max corners (+7/+10) remain feasible.

## Directions for a real fix (not implemented)

Prefer in this order; all stay CP-SAT + iterate-and-exclude + pack flags:

1. **Structured generated charm** — one (or few) templates per type: IntVars
   for skill-1/2 tree, points, slots, constrained by CSV envelopes. No
   cartesian `CharmSpec` table.
2. **Query-tight domain** — only trees that can reduce the residual after a
   cheap armor/jewel bound; drop pairs that cannot help any requested
   threshold.
3. **Athena ReduceCharm as a second solve** — find any feasible charm, then
   minimize `charm_strength` (already objective 1) on a tiny neighborhood.
4. **Do not** raise the default 2 s budget as the primary fix (MHGU Phase 3
   still gates on 2 s). A per-request override is fine for experiments.
5. **Do not** restore per-charm worker threads or unbounded result buffers.

## Pointers

- Engine contract: `docs/specs/engine-spec.md` §2 charm variable, §3
  weakest-charm, §5 budgets.
- Skill: `.cursor/skills/extend-solver-model/SKILL.md`.
- Pack data: `packs/mhp3/charm_generation/`, `docs/legacy-analysis/MHP3-ASS.md`.
