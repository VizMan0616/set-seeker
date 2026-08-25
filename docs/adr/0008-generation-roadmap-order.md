# ADR 0008: Generation rollout order

- Status: accepted
- Date: 2026-08-24

## Context

Six game packs, built sequentially (never in parallel). The maintainer has the most hands-on
experience — and therefore the best ability to stress-test correctness — in MHFU and MHP3.

## Decision

Rollout order:

1. **MHFU** — no charm dimension, smallest dataset (~410 pieces/slot), simplest solver model.
   Validates ETL + CP-SAT + htmx UI end-to-end at minimum complexity.
2. **MHP3** — adds the charm dimension (inventory + generated legal charms) and the
   fan-translation data caveat.
3. **MHGU** — the engine superset and largest dataset (~1200 pieces/slot): Charm Up, Skill +2,
   compound skills, 4 charm types. The stress test for the solver.
4. **MH3U** — adds the 17-table charm selection and hardcoded-table ETL extraction.
5. **MH4** — adds excavated gear and the weapon search dimension.
6. **MH4U** — widest model (6 charm types, relics, weapons); last because it inherits
   everything proven above.

Full rationale and per-generation deltas: `docs/roadmap.md`.

## Consequences

- Every generation after MHFU only *adds* solver dimensions; nothing is reworked.
- MHGU landing third means the solver's ceiling is validated early, before the gen-4 packs.
- Save-file decryption is evaluated per generation when its turn comes (`docs/adr/0006`).
