# AGENTS.md — how to work in this repository

Read `CONTEXT.md` first. It defines the domain language and the hard constraints
(Bootstrap only, no Tailwind, no JS build step, single-container Docker, AGPLv3).

## Task routing — read only what you need

| If your task is about... | Read |
|---|---|
| Understanding the project, domain terms, constraints | `CONTEXT.md` |
| Why the legacy tool is slow / what patterns to avoid | `docs/legacy-analysis/overview.md` |
| A specific legacy repo's algorithm or data format | `docs/legacy-analysis/<GAME>-ASS.md` |
| Implementing or changing the armor search engine | `docs/specs/engine-spec.md` + the relevant `docs/legacy-analysis/<GAME>-ASS.md` |
| Adding a new game / generation | `docs/prompts/README.md` then `docs/prompts/implement.md` (or `review.md`) |
| Historical Phase 0/1 parallel-build interfaces | `docs/specs/phase0-contracts.md` — as-built is `app/` |
| Village / guild rank caps for a pack | `CONTEXT.md` (table) — do not re-scan ASS |
| Database schema, ETL, queries, swapping SQLite→MariaDB | `docs/specs/database-schema.md` |
| Why a decision was made | `docs/adr/` (each ADR is self-contained) |
| What to build next | `docs/roadmap.md` |
| Provenance/licensing of legacy code and data | `SOURCES.md`, `NOTICE`, `LICENSE` |

Do not bulk-read `docs/` — each document is written to be self-sufficient for its task type.

## Project skills

Committed under `.cursor/skills/` — apply them when their trigger matches:

- `add-game-pack` — adding a generation / starting a roadmap phase
- `extend-solver-model` — changing the CP-SAT search model
- `run-etl` — building or debugging the data ETL
- `legacy-oracle` — verifying behavior against the legacy tools

## Rules

1. **Never modify anything under `sources/`.** Those are local-only upstream clones
   (gitignored; restore via `SOURCES.md`). Cite them with file path + line numbers.
2. **Decisions in `docs/adr/` are settled.** If a task conflicts with an ADR, stop and surface
   the conflict to the user; a superseding ADR is required to change course.
3. **Bootstrap only. No Tailwind, ever.** No npm/node build pipeline; JS is limited to
   htmx/Alpine via CDN or vendored static files.
4. **Deployment stays one-container.** Any change that adds a required service needs an ADR.
5. The legacy code is C++/CLI, not C#. When porting logic, port the *behavior* described in
   `docs/specs/engine-spec.md`, not the brute-force structure.
6. Keep upstream attribution intact: `NOTICE` must stay, and any copied data files carry the
   AthenaADP MIT license.

## Current state

MHFU (Phase 0/1) and MHP3 (Phase 2) ship. Application code lives under `app/`;
shipped packs are `packs/mhfu/` and `packs/mhp3/`. Adding a generation: use the
`add-game-pack` skill (and `extend-solver-model` when the pack turns on a mechanic
the engine does not yet model). Reviewer sessions use the same skills to grill
against ADRs and specs, not to rewrite.
