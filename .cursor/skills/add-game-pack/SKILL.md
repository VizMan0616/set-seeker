---
name: add-game-pack
description: Add support for a new Monster Hunter generation (game pack) to set-seeker. Use when the user asks to add a game, create a pack (mhfu, mhp3, mh3u, mh4, mh4u, mhgen, mhgu), or start a roadmap phase.
---

# Add Game Pack

## Rules (non-negotiable)

1. **No per-game branches in engine code.** New mechanics arrive as pack manifest flags +
   data only (ADR 0001). If a mechanic seems to require engine changes, it is a solver-model
   extension — use the `extend-solver-model` skill instead.
2. Follow the phase order in `docs/roadmap.md`; packs are built sequentially, never in
   parallel.
3. A pack is done only when its known-query suite passes against the legacy tool
   (`docs/specs/engine-spec.md` §7).

## Workflow

1. Read `docs/specs/data-pack-spec.md` — manifest format, source file formats, ETL rules.
2. Read the pack's deep dive: `docs/legacy-analysis/<GAME>-ASS.md` — per-game format quirks
   (header lines, index columns, slot notation, charm data location).
3. Read the roadmap phase entry for this pack in `docs/roadmap.md` — flags to set, mechanics
   to enable, save-import deferral line item.
4. Verify `sources/<GAME>-ASS/` exists; if missing, restore it via the commands in
   `SOURCES.md` (pinned commit) before touching ETL.
5. Write the pack manifest (flags from the matrix in `docs/specs/data-pack-spec.md`), the
   per-pack column map, and the ETL wiring.
6. Add ≥3 known queries with expected legacy results to the pack's validation suite.
7. Run ETL, run the validation gate, then update the pack's legacy-analysis doc if ETL
   uncovered format details the analysis missed.

## References

- `docs/specs/data-pack-spec.md` — formats and ETL rules
- `docs/specs/database-schema.md` — target tables
- `docs/adr/0001`, `docs/adr/0006`, `docs/adr/0008` — settled constraints
