---
name: run-etl
description: Build, rebuild, or debug the set-seeker game-data ETL that converts legacy Athena's ASS data files into the SQLite schema. Use when the user mentions ETL, rebuilding the database, importing pack data, data looking wrong, or Docker build data steps.
---

# Run ETL

## Rules (non-negotiable)

1. **Per-pack column maps.** Never share positional parsing across packs; each manifest
   declares its quirks (header lines, leading index columns, `O--` slot notation). This is
   the most common ETL bug.
2. **Idempotent.** ETL drops and rebuilds game-data tables only. It never touches user tables
   (`sessions`, `user_charms`, `search_states`).
3. **Portable SQL only** (ADR 0004): SQLAlchemy Core, no SQLite-specific statements — MariaDB
   must remain a drop-in swap.
4. **Validation gate:** after load, run the pack's known-query suite. A failed gate means the
   build failed — do not ship data that fails it.

## Workflow

1. Read `docs/specs/data-pack-spec.md` — source formats, ETL rules, manifest fields.
   Progression caps are already listed there (and in `CONTEXT.md`); write those
   integers into `progression.*` — do not infer them from max `hr` / village columns.
2. Confirm `sources/<GAME>-ASS/` is present at the pinned commit (`SOURCES.md`); restore if
   missing.
3. For mh3u/mhp3: charm tables are hardcoded C++ — run the one-time extraction into pack data
   first (`docs/specs/data-pack-spec.md`, "charm tables" section).
4. Run the ETL for the target pack(s); then run the validation gate.
5. On data mismatches: diff against the legacy file cited in
   `docs/legacy-analysis/<GAME>-ASS.md` before touching parser code — most mismatches are
   column-map drift, not parser bugs. For MHFU **names**, the CSV is TeamHGG-style;
   `name_en` must match `Languages/English MHFU` (official), not the CSV/`TeamHGG MHP2ndG`
   strings.

## References

- `docs/specs/data-pack-spec.md` — formats and rules
- `docs/specs/database-schema.md` — target schema and portability contract
- `docs/adr/0004` — SQLite/MariaDB decision
