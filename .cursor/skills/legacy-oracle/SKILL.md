---
name: legacy-oracle
description: Verify set-seeker behavior against the legacy Athena's ASS tools, or answer questions about legacy behavior. Use when the user asks whether a result is correct, how the original tool did something, or to compare/replay queries against Athena's ASS.
---

# Legacy Oracle

The legacy tools are the correctness reference. Answer from the analysis docs first; open the
C++/CLI sources only to verify or extend them.

## Workflow

1. Start with `docs/legacy-analysis/overview.md` — shared pipeline, root causes, what we keep.
2. Then the per-game deep dive `docs/legacy-analysis/<GAME>-ASS.md` — algorithm walkthrough,
   data formats, charm model, all with file:line citations into `sources/`.
3. Only if those are insufficient: read `sources/<REPO>/` directly (read-only; restore via
   `SOURCES.md` if absent). Never modify anything under `sources/`.
4. To judge a set-seeker result: replay the same query through the pack's known-query suite
   (`docs/specs/engine-spec.md` §7). Divergence = bug in our model or data, unless it traces
   to a documented legacy bug (e.g. weak dedup hash collisions, disabled result caps).

## Quick index into the legacy code

| Concern | Where (all repos, same layout) |
|---|---|
| Search worker loops | `Form1.h` `backgroundWorker1_DoWork` |
| Match + decoration fill | `Solution.cpp` `MatchesQuery` / `CalculateDecorations` |
| Pruning | `LoadedData.cpp` `GetRelevantData` |
| Charm tables/generation | `CharmDatabase.cpp` (+ `Run/Data/Charm Generation/*.csv` gen 4+) |
| Data parsers | `Armor.cpp`, `Decoration.cpp`, `Skill.cpp` |

Per-repo line numbers are in each deep dive — use them instead of re-searching the sources.

## Known legacy bugs (do not "fix" our output to match)

- Result-cap early exits commented out (MHP3 `Form1.h:1916-1921` and siblings).
- "Showing first 1000" message does not truncate the rendered text.
- Weak armor dedup hash (`index << (i*3)`) — collision-prone.
- `MessageBox::Show` from worker threads.
