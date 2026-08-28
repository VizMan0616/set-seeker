# Implementer prompt (copy everything below the line)

Fill the three slots. Do not add extra context unless NOTES requires it.

---

```
GENERATION: <mhfu|mhp3|mh3u|mh4|mh4u|mhgen|mhgu>
SCOPE:      <etl|engine-ui|integrate>
NOTES:
```

You are the **sole implementer** for this SCOPE. Fresh chat; do not assume prior sessions.

## Skills (invoke these; do not re-derive their rules)

- `SCOPE: etl` → **add-game-pack** + **run-etl**
- `SCOPE: engine-ui` → **extend-solver-model** (and **add-game-pack** only for Advanced Search / UI flag checklist)
- `SCOPE: integrate` → none required; read the Done checklist below

## Open only these (in order)

1. `AGENTS.md` then `CONTEXT.md` (constraints).
2. `docs/roadmap.md` — this GENERATION's phase only.
3. Skill-required specs:
   - etl: `docs/specs/data-pack-spec.md`, `docs/legacy-analysis/<GENERATION>-ASS.md`
   - engine-ui: `docs/specs/engine-spec.md` §6 + the same legacy-analysis file
   - integrate: `docs/specs/phase0-contracts.md` §8–§9 (as-built notes in its banner)
4. Restore `sources/<REPO>-ASS/` from `SOURCES.md` if missing. **Never edit `sources/`.**

Do not bulk-read `docs/`. Do not open other generations' analysis files.

## Hard rules

- No per-game `if game == …` in `app/engine/`. Flags + data only (ADR 0001).
- No Tailwind, no npm, no new required services, no new dependencies without asking.
- Portable SQL only (ADR 0004). Engine stays pure (`app.domain` + `app.engine.data`).
- Save-file decryption is out of scope unless NOTES says otherwise (ADR 0006).

## Do this SCOPE

**etl** — `packs/<id>/` (manifest, known_queries), `app/etl/column_maps/<id>.py`, loaders/writer wiring, `python -m app.etl --pack <id>`, gate green. Follow the existing MHFU pack as the shape. Progression caps come from `CONTEXT.md` (do not re-scan armor for max HR).

**engine-ui** — Only mechanics this pack turns **on** that the engine does not already honor. Reuse Advanced Search / catalog patterns already in `app/web/`. Charm inventory UI only if `talismans: true`. Tests: engine assertions + one web path that exercises the new flag.

**integrate** — Wire pack into game picker / Docker (copy `sources/<REPO>`, `etl --pack <id>`), run full pytest + ETL gate, smoke one real query, update `CONTEXT.md` current-state and this generation's legacy-analysis if ETL found format drift.

## Done

- Tests you added or touched pass.
- Report: files changed; any contract/ADR conflict you did **not** guess your way through; follow-ups for the other SCOPE.
