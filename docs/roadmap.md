# Roadmap — generation rollout

Order and rationale are decided in `docs/adr/0008`. Generations are built **sequentially,
never in parallel**. Each phase: implementer `SCOPE: etl` → reviewer → (if new engine
flags) implementer `SCOPE: engine-ui` → reviewer → integration reviewer. Prompts:
`docs/prompts/`.

## Phase 0 — Walking skeleton (done)

Shipped with Phase 1. As-built: `app/`, `Dockerfile`, `alembic/`. The parallel-agent
contract in `docs/specs/phase0-contracts.md` is historical; new generations use
`docs/prompts/`.

## Phase 0 (original checklist, kept for provenance)

- FastAPI app shell: Jinja2 + Bootstrap + htmx, anonymous session middleware.
- SQLAlchemy Core + Alembic + repository layer (`docs/specs/database-schema.md` — portability
  contract is enforced from the first commit).
- ETL framework reading a pack manifest (`docs/specs/data-pack-spec.md`).
- CP-SAT engine skeleton implementing `docs/specs/engine-spec.md` end to end for one slot set.
- Dockerfile: multi-stage, ETL at build time, single runtime container.

## Phase 1 — MHFU (gen 2) — done

Shipped: ETL, CP-SAT search, Advanced Search, set-mix / known-query gates, Docker.
Only remaining MHFU work is optional (more known queries from live Athena runs).

## Phase 1 (original checklist)

- **Why first:** no charm dimension, smallest dataset (~410 pieces/slot), simplest model.
- Pack flags: `talismans: false`, everything else off.
- ETL: `.csv` armor files (2 header lines, `O--` slots), block-format `skills.txt`,
  header-less `decorations.csv`.
- Validation: ≥3 known queries replayed against legacy MHFU-ASS v3.43b output.
- Save import: N/A (no charms).

## Phase 2 — MHP3 (gen 3)

- **Adds:** charm variable (user inventory + generated legal charms), weakest-charm objective,
  charm inventory UI (mobile-fast entry per `docs/adr/0006`).
- ETL: `.txt` armor files, skills with Japanese columns, charm RNG table data extraction from
  `CharmDatabase.cpp` into pack data.
- Data caveat: English names are fan translations (`translation: fan` in manifest,
  `docs/adr/0009`).
- Save import (PSP decryption, `PSPCryptoEngine.cpp`): **deferred** — evaluate when this phase
  ships; not required for the phase to be complete.

## Phase 3 — MHGU (gen "5-classic")

- **Why third:** the engine superset and the largest dataset (~1200 pieces/slot) — the solver
  stress test, landed early on purpose.
- **Adds:** Charm Up (charm skills doubled), Skill +2, compound skills, 4 charm types
  (mystery/shining/ancient/enduring).
- ETL: `Charm Generation/*.csv`, `compound_skills.txt`.
- Performance gate: worst-case published-style queries must solve within the default 2 s
  budget on modest hardware.
- Save import (`SaveData.*`): deferred, per-phase evaluation.

## Phase 4 — MH3U (gen 3)

- **Adds:** 17-table charm selection as a query filter over legal charms.
- ETL: extraction of the hardcoded charm tables (`CharmDatabase.cpp` ~284+, seeds at ~979)
  into `mh3u_charm_tables`; skills files with leading index columns.
- Save import: deferred, per-phase evaluation.

## Phase 5 — MH4 (gen 4)

- **Adds:** excavated/relic gear (user-registered equipment list, analogous to charm
  inventory), weapons as a 6th solver variable group.
- ETL: 4 charm types incl. distorted; skills without leading index columns.
- Save import: deferred, per-phase evaluation.

## Phase 6 — MH4U (gen 4)

- **Adds:** 6 charm types (+ enduring, graven), relic weapons/armor at gen-4 scale,
  `savedata_format.txt` ability ordering.
- Last because it inherits every mechanism proven above; mostly a data + flags exercise.
- Save import (Blowfish `Crypto/`): deferred, per-phase evaluation.

## Cross-phase rules

- A phase is done only when its known-query suite passes against the legacy tool
  (`docs/specs/engine-spec.md` §7).
- No per-game branches in engine code; new mechanics arrive as pack flags + data.
- Each phase updates its pack's `docs/legacy-analysis/<GAME>-ASS.md` citations if ETL work
  uncovers format details the initial analysis missed.
