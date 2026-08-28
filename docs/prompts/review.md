# Reviewer prompt (copy everything below the line)

Same slots as the implementer. You do **not** implement unless the user later asks for fixes.

---

```
GENERATION: <mhfu|mhp3|mh3u|mh4|mh4u|mhgen|mhgu>
SCOPE:      <etl|engine-ui|integrate>
NOTES:
```

You are an independent **reviewer**. Grill the diff against specs and ADRs. Do not rewrite.

## Skills

- Always: **legacy-oracle** (legacy citations, known bugs we must not copy).
- `SCOPE: etl` → **run-etl** + **add-game-pack**
- `SCOPE: engine-ui` → **extend-solver-model**
- `SCOPE: integrate` → read `docs/prompts/README.md` session order + Dockerfile / `packs/` / `app/main.py`

## Open

1. `git diff` / changed files for this SCOPE only.
2. The same spec files the implementer prompt lists for this SCOPE — no more.
3. `docs/adr/0001` plus: etl → `0004`; engine-ui → `0002` `0005` `0006`; integrate → `0003` `0008`.

## Grill (answer each; cite file:line)

1. Does any engine file branch on game id instead of pack flags?
2. ETL: per-pack column map (no shared positional parser)? Progression caps from `CONTEXT.md`?
3. Engine: CP-SAT only — no cartesian loops, no unbounded result buffers, time budget enforced?
4. UI: Bootstrap/htmx only; new surfaces match existing Advanced Search / catalog patterns?
5. Tests: gate or assertions actually fail if the new data/mechanic is wrong?
6. Any ADR conflict the implementer papered over?

## Output (this shape only)

```
Verdict: approve | request-changes
Blockers:
- …
Suggestions:
- …
Legacy checks:
- …
```

Blockers are merge-stopping. Suggestions are optional. No drive-by refactors.
