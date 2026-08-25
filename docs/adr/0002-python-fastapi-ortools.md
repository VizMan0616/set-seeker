# ADR 0002: Python + FastAPI + OR-Tools CP-SAT

- Status: accepted
- Date: 2026-08-24

## Context

The legacy search is CPU-bound combinatorial enumeration that froze PCs even in C++/CLI
(`docs/legacy-analysis/overview.md`). Language options:

1. **Go**: near-1:1 port of the legacy loops, tiny static binary — but outside the maintainer's
   daily language.
2. **Python + OR-Tools CP-SAT**: replace brute force with a constraint solver; stay in the
   maintainer's primary language.
3. **Python + hand-optimized search** (bitsets, branch-and-bound, multiprocessing): no big
   deps, highest risk of repeating the legacy performance problem.
4. **Python web layer + Go search sidecar**: two languages in one repo.

## Decision

Python + FastAPI + OR-Tools CP-SAT. The armor/charm/decoration selection is modeled as a
constraint-satisfaction problem (`docs/specs/engine-spec.md`); the solver replaces the nested
loops entirely and provides native pruning, optimization objectives (weakest-charm-first), and
wall-clock limits.

## Consequences

- The legacy heuristics (greedy decoration fill, charm reduction) are re-expressed as
  constraints/objectives — an exactness upgrade, but they must be re-validated against the
  legacy tools (known-query suite).
- OR-Tools is a heavy dependency; acceptable inside a Docker image.
- Solver work must stay off the request thread pool's mercy: per-solve time budgets are a hard
  rule (`docs/specs/engine-spec.md` §5).
- Python's raw loop speed no longer matters: no Python code runs per candidate combination.
