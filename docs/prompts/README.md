# Agent prompts — how to run a generation

Two copy-paste templates, same slots. Do **not** write a new prompt per game.

| File | Who |
|---|---|
| [orchestrate.md](orchestrate.md) | **Preferred:** one parent chat that launches children and waits |
| [implement.md](implement.md) | A child implementer (or a solo chat if you are not using Multitask) |
| [review.md](review.md) | A child reviewer |

## Slots

```
GENERATION: mhfu | mhp3 | mh3u | mh4 | mh4u | mhgen | mhgu
SCOPE:      etl | engine-ui | integrate
NOTES:      (optional; leave blank)
```

## Session order (one generation)

1. **Implementer A** — `SCOPE: etl` (pack files, column map, ETL, gate).
2. **Reviewer A** — same `GENERATION` + `SCOPE: etl`.
3. Fix / merge A only when the reviewer has no blockers.
4. **Implementer B** — `SCOPE: engine-ui` (solver + UI for **new** pack flags only).
   Skip this pair if the pack adds no engine mechanic the code already models.
5. **Reviewer B** — `SCOPE: engine-ui`.
6. **Integration reviewer** — `SCOPE: integrate` (wiring, Docker, smoke, docs).

B never starts until A's ETL gate is green and merged.

**Preferred UX:** one chat, paste [orchestrate.md](orchestrate.md). The parent
launches implement/review children **in order**. Do not open sibling chats and
do not tell a child to wait — the parent is the only waiter.

**Fallback:** paste implement/review yourself into separate chats if you are not
using Multitask. You become the orchestrator.

## Token rule

Paste the template, fill three lines, send. Do not paste specs into the chat —
the template tells the agent which files to open.
