---
name: extend-solver-model
description: Extend or modify the set-seeker CP-SAT search model (new mechanics like Charm Up, excavated weapons, new constraints or objectives). Use when the user asks to change how armor set search works, add a solver variable/constraint/objective, or fix incorrect search results.
---

# Extend Solver Model

## Rules (non-negotiable)

1. The engine is CP-SAT (OR-Tools). **Never reintroduce brute-force enumeration, per-charm
   worker fan-out, or unbounded result accumulation** — the legacy failure modes are listed in
   `docs/legacy-analysis/overview.md` ("Patterns to never repeat").
2. Every solve keeps a wall-clock budget and request-scoped cancellation
   (`docs/specs/engine-spec.md` §5). New variables/constraints must not bypass this.
3. Enumeration stays iterate-and-exclude (ADR 0005). Do not add solution pools or result
   buffers.
4. Mechanics are flag-gated per pack (`docs/specs/engine-spec.md` §6); the engine reads flags,
   it does not branch on game ids.

## Workflow

1. Read `docs/specs/engine-spec.md` — the variable/constraint/objective contract.
2. Read the relevant legacy deep dive (`docs/legacy-analysis/<GAME>-ASS.md`) for the
   mechanic's reference behavior; cite `sources/<REPO>/<path>:<line>` when porting semantics.
3. Express the mechanic as variables + constraints, or as an objective term. Legacy greedy
   heuristics (decoration fill, charm reduction) become constraints/objectives, not
   procedural code.
4. Check the per-generation delta matrix (`engine-spec.md` §6) and set the pack flag.
5. Extend the pack's known-query suite with a case that exercises the new mechanic; all
   suites must pass.

## Objective order (settled)

1. Minimize required charm strength → 2. Maximize spare slots → 3. Maximize defense →
4. Query sort tie-breakers. Changing this order requires a new ADR superseding ADR 0005.

## References

- `docs/specs/engine-spec.md` — the contract
- `docs/adr/0002`, `docs/adr/0005` — settled decisions
- `docs/legacy-analysis/overview.md` — what we are replacing and why
