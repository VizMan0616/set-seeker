# MH4U-ASS — MH 4 Ultimate (gen 4), v1.13b

Upstream: https://github.com/AthenaADP/MH4U-ASS @ `4837fe40` — MIT (AthenaADP 2017).
Source root: `sources/MH4U-ASS/`. Solution: `MH4G ASS.sln` / `MH4G ASS.vcxproj`
(v141, `CLRSupport`, Win SDK 8.1).

## Structure

- C++/CLI WinForms, ~14.4k LOC.
- Heaviest: `Form1.h` (~3,154), `CharmDatabase.cpp` (~1,694), `Solution.cpp` (~1,299).
- Unique: `Crypto/` (Blowfish save decryption), `ManageEquipment.*`, excavated gear,
  `savedata_format.txt`.
- Data: ~1.5 MB under `Run/Data/`; ~600–640 armor rows/slot; 202 decorations; 278 skills;
  **6 charm types** (mystery, shining, ancient, distorted, enduring, graven).

## Search algorithm

Orchestration: `Form1.h` `StartSearch` (~1720–1826), worker `backgroundWorker1_DoWork`
(~2463–2562). Pruning: `LoadedData::GetRelevantData` (`LoadedData.cpp:~243-319`).
Feasibility: `Solution::MatchesQuery` (`Solution.cpp:~967-1059`).

1. **Query** (`FormulateQuery`, `Form1.h:~1552-1588`): skill combos, HR/VE, gender, hunter
   type, options.
2. **Prune**: relevant abilities → relevant decorations → armor filtered by
   HR/event/gender/type (`Armor::MatchesQuery` ~207–257), dominance prune via
   `AddToList` (`LoadedData.cpp:~113-161`). Keeps "inf" lists for Advanced Search.
3. **Charm work units**: one worker per charm template (none / my charms / slot-only /
   generated 1-skill / 2-skill) — `StartSearch` ~1764–1825.
4. **6 nested loops**: head×body×arms×waist×legs×weapons (`Form1.h:2490-2553`).
5. `MatchesQuery`: sum skills/slots (torso multiplier, charm, weapon) → early reject if
   impossible without decos → greedy `CalculateDecorations` → threshold check → optional
   bad-skill fix / charm reduction / spare-slot extras.
6. Results merged with hash dedupe; hard cap `MaxSolutions = 100000`.

Complexity: Θ(|H|·|B|·|A|·|W|·|L|·|Weapons| · C) after pruning; each combo pays decoration
logic.

## Performance problems

| Issue | Location |
|---|---|
| 6-deep brute-force loops | `Form1.h:2490-2553` |
| One worker per charm; only `ProcessorCount` run at once | `QueueTask`/`StartSearch`, `StartTasks` ~1706–1717 |
| `gcnew Solution()` per combo | `Form1.h:2522-2529` |
| Full decoration recompute per combo, no incremental DP | `MatchesQuery` → `CalculateDecorations` |
| Progress only on head×body | `Form1.h:2494-2507` |
| `MessageBox::Show` on worker | `Form1.h:2545-2548` |
| Result dump into one RichTextBox | `UpdateResultString` ~2019–2200 |
| No early exit on `MAX_LIMIT` (commented out) | `Form1.h:2537-2542` |
| Cooperative cancel checked at innermost loop only | `CancelAsync` + `CancellationPending` |

## Data storage (`Run/Data/`)

Core files as in MH4 (armor per slot, decorations, skills without leading index columns,
compound_skills, components, tags, `Languages/*/`).

Charm CSVs (`Run/Data/Charm Generation/`): `{type}_skill1.csv` (ability, min, max),
`{type}_skill2.csv`, `{type}_slots.csv` (fulfillment thresholds for 1/2/3 slots), loaded by
`LoadCharmTableData()` (`CharmDatabase.cpp:~1115-1139`). Six types: mystery, shining, ancient,
distorted, enduring, graven.

MH4U-only: `savedata_format.txt` (ability order for save import), `Crypto/` Blowfish save
parsing, `Data/mycharms.txt` (`Slots,Skill1,Points1,Skill2,Points2`).

## Talismans

Dual model, as in all gen 3+ repos:

1. **User charms** — `CharmDatabase::mycharms` ↔ `Data/mycharms.txt`; Manage Charms UI; save
   import via Blowfish `Crypto/`.
2. **Procedural tables** — CSVs → `GetCharms(query, twoSkill)` (`CharmDatabase.cpp:~1578`):
   legal 1-skill, optional 2-skill, slot-only charms for the requested skills.

UI modes (`cmbCharmSelect`): no charms / my charms only / slotted only / ≤1 skill / 2 skill.
One charm template per worker; `Charm::AddToOptimalList`/`StrictlyBetterThan` prune dominated
user charms.

## Decorations

Loaded into `Decoration::static_decorations` + ability map; query keeps `rel_decorations` for
needed skills (+ taunt gems if Sense/Taunt requested). Greedy placement by slot size (3→2→1),
body first with torso multiplier (`AddDecorations23`/`AddDecorations1`,
`Solution.cpp:~358-610`). 1-slot gem swaps fix bad skills (`FixBadSkill`/`ReorderGems`).
Advanced Search can force-enable/disable individual jewels.

## Results UI

RichTextBox dump; display cap `MAX_LIMIT` (default 1000, Options → Max Results); hard search
cap 100k. Sort (`SortResults` ~2799–2826): resists, def, max def, difficulty, rarity, slots
spare, family, extra skills. Filters: charm name combo, extra-skill combo. Mid-search: progress
bar + "Solutions found: N"; Ctrl+F find.

## Rewrite notes

- Richest gen-4 dataset; the 6-charm-type CSV set is the most complete charm-generation data
  and should be the reference for the gen-4 data-pack ETL.
- Blowfish save import (`Crypto/`) is deferred per-generation scope — see `docs/adr/0006`.
- Excavated gear + weapon dimension make this the widest legacy search model; our solver treats
  weapons as an optional variable group.
