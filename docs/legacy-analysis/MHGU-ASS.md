# MHGU-ASS — MH Generations Ultimate / MHXX, v1.02b

Upstream: https://github.com/AthenaADP/MHGU-ASS @ `ae7f125d` (2019-08-18, latest commit of all
six repos) — MIT (AthenaADP 2017). Source root: `sources/MHGU-ASS/`.
`GAMES L"MHXX and MHGU"`. .NET 4.5, Win SDK 10.0.15063.0.

## Structure

- C++/CLI WinForms, ~13.6k LOC.
- Heaviest: `Form1.h` (~3,440), `Solution.cpp` (~1,416), `CharmDatabase.cpp` (~1,383).
- Extra engine vs MHGen: **Charm Up / Skill Point +2 / full Neset set** support
  (`DoWork2` ~2706, `charm_up_armors_*`).
- Data: **~2.5 MB — the largest pack**; ~1150–1240 armor rows/slot (~2× MHGen); 242
  decorations; 327 skills; **4 charm types** (mystery, shining, ancient, enduring).
- Progression caps (Athena `nudHR` / `nudElder`): **guild HR 13, village ★10**
  (`Form1.h:1090,1104`). G-rank hub ★9–13. Closed-path sentinel is 99.

## Search algorithm

Orchestration: `Form1.h` `StartSearch` / `backgroundWorker1_DoWork` (~2757+), plus
**`DoWork2` (~2706)** — a second worker path for Charm Up sets (fixed full-set searches over
`charm_up_armors_*`). Otherwise the shared pipeline:

1. Query (`NumSkills = 7`, `Form1.h:87`; static combo boxes) → relevance + dominance prune (`LoadedData::GetRelevantData`).
2. One worker per charm template.
3. 5 nested armor loops (`Form1.h:~2779+`).
4. `Solution::MatchesQuery` — same greedy decoration pipeline; **charm skills are doubled when
   Charm Up is active**; Skill +2 adds +2 to all skill trees.
5. Hash dedupe, `MaxSolutions = 100000`.

Complexity: same Θ(product of pruned lists × charm templates), but the raw catalog is
~1200 pieces/slot — worst-case wall time of all six repos. This is the pack that most
justifies replacing brute force with CP-SAT.

## Performance problems

Same family as MH4U/MHGen (5-deep loops, per-charm workers, per-combo allocation, monolithic
RichTextBox dump, commented-out early exit, coarse cancel), aggravated by:

| Issue | Notes |
|---|---|
| ~2× pieces/slot vs MHGen | Same algorithm, ~worst wall time of the six |
| Charm Up second search path (`DoWork2` ~2706) | Extra fixed full-set searches on top |
| Largest data files (~2.5 MB) | Longest load + prune time |

## Data storage (`Run/Data/`)

Core files as in MH4/4U/Gen. Charm CSVs for 4 types (adds `enduring_*`). User charms in
`Data/mycharms.txt`. Language overlays under `Languages/*/` (the pinned commit is an Italian
translation update — the most actively maintained repo of the six).

## Talismans

Dual model (user charms + CSV-driven procedural tables), `GetCharms` at
`CharmDatabase.cpp:~1267`. Charm Up doubling is applied in `Solution::GetInitialData`
(`Solution.cpp:~268-333`).

## Decorations

Greedy 3→2→1 with torso multiplier; bad-skill swaps; Advanced Search overrides. 242
decorations — the largest jewel catalog of the six.

## Results UI

RichTextBox dump, `MAX_LIMIT` display cap (default 1000), 100k ingest cap, full sort combo,
charm/extra-skill filters, no pagination.

## Rewrite notes

- **The engine superset.** Per the cross-repo analysis: "port logic from MHGU (superset) or
  factor MH4U extras (excavated) as plugins." Our solver spec (`docs/specs/engine-spec.md`)
  uses MHGU's mechanics as the ceiling: charms, Charm Up, Skill +2, compound skills.
- Third pack in the roadmap (after MHFU and MHP3) precisely because it stress-tests the solver
  with the largest dataset (`docs/roadmap.md`).
- Compound skills (`compound_skills.txt`) — one skill tree that auto-grants several others —
  must be modeled in the ETL/solver as skill-tree expansion, not as separate pieces.
