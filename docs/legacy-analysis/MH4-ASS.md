# MH4-ASS — MH 4 (gen 4), v1.06b

Upstream: https://github.com/AthenaADP/MH4-ASS @ `e50ea824` — MIT (AthenaADP 2017).
Source root: `sources/MH4-ASS/`. Solution: `MH4 ASS.sln` (both `.vcproj` .NET 3.5 and
`MH4 ASS.vcxproj` v141/Win8.1 SDK).

## Structure

- C++/CLI WinForms, ~11,824 LOC.
- Heaviest: `Form1.h`, `CharmDatabase.cpp`, `Solution.cpp`.
- Adds vs MH3U: `ManageEquipment.*`, `SkillHelp.*`, excavated gear, weapon loop in search.
  Forms renamed: `About`/`Advanced`/`Find`/`ImportCharms` (was `frm*`).
- Data: external under `Run/Data/`, **plus `Run/Data/Charm Generation/*.csv`** (new in gen 4).
- Progression caps (Athena `nudHR` / `nudElder`): **guild HR 8, village ★7**
  (`Form1.h:803,856`). High-rank only (hub ★8, not 7). Closed-path sentinel is 99.

## Search algorithm

Same architecture as MH3U; worker at `Form1.h:2182-2274`.

**Key difference — 6 nested loops**: head×body×arms×waist×legs×**weapons**
(`Form1.h:2207-2270`), active when excavated weapons are relevant
(`LoadedData.cpp:229-237`).

`Solution::MatchesQuery` (`Solution.cpp:839+`): same greedy decoration pipeline; adds
excavated/weapon ability contribution and `AddExtraSkills`/`potential_extra_skills`
("spend spare slots" suggestions).

Complexity: O(|H|·|B|·|A|·|W|·|L|·|Weapons|·C).

## Performance problems

Same patterns as MH3U, plus:

| Issue | Location |
|---|---|
| 6-deep loops including weapons | `Form1.h:2207-2270` |
| Hard stop at `MaxSolutions = 100000` while searching | `Form1.h:81`, `AddSolutions` 2051–2057 |
| Worker `MessageBox` | `Form1.h:2262-2265` |
| Per-combo allocation | `Form1.h:2239-2246` |
| Early MAX_LIMIT exit still commented out | `Form1.h:2254-2259` |
| Weaker armor hash (`index << (i*3)` vs MH3U's `i*12`) | `Form1.h:2005-2012` |

## Data storage (`Run/Data/`)

Same `.txt` layout as MH3U, with two format changes:

- **`skills.txt` drops the leading ping/index columns**: `name, ability, points, type, tags…`
  (`Skill.cpp:102-117`). ETL column maps differ between gen 3 and gen 4+.
- **Charm generation externalized to CSVs** under `Run/Data/Charm Generation/`:

| File | Columns |
|---|---|
| `{mystery,shining,ancient,distorted}_skill1.csv` | スキル系統 (skill tree), 最小 (min), 最大 (max) |
| `*_skill2.csv` (except mystery) | same |
| `*_slots.csv` | 充足値 (fulfillment), s1/s2/s3 判定値 (slot thresholds) |

Loaded by `LoadCharmTableData` (`CharmDatabase.cpp:1000-1025`). Also:
`skill_descriptions.txt` (languages), excavated equipment save/load.

## Talismans

- Same five search modes; **no `cmbCharmTable` on the main UI** (`charm_table` removed from
  `Query` in `Solution.h`).
- Legality/generation still uses **17 table seeds** (`CharmDatabase.h:37`) + the CSV skill/slot
  tables.
- Slotted-charm mode uses HR/village thresholds only (`Form1.h:1614-1625`); old
  `have_slots[...]` checks commented out.
- `FindCharmLocations`/seed lists support "where can I get this charm" tooling.
- User charms: `mycharms` + `LoadCustom`/`SaveCustom` (`CharmDatabase.cpp:165+`).
- **ExcavatedGear** (`CharmDatabase.h:22-29`): user-registered relic armor/weapons join the
  search when allowed.

## Decorations

Same greedy packing as MH3U. Decorations include `jap_name`; filters include arena/excavated
options.

## Results UI

Same RichTextBox dump, `MAX_LIMIT` (default 1000), sort combo, charm filter, no pagination.
Prints a weapon line when present (`Form1.h:~2599`). Hard ingest cap 100k solutions.

## Rewrite notes

- MH4 proves the engine's data was *meant* to be externalized: charm tables moved from
  hardcoded arrays (MH3U) to CSVs. Our ETL continues that direction into SQLite.
- Excavated/relic gear is a per-game feature flag (`excavated_gear: true`) with a user-managed
  equipment list — analogous to charm inventories (`docs/specs/data-pack-spec.md`).
- The weapon loop is a gen-4-only 6th search dimension; in the solver it is an optional
  variable group, not a nested loop.
