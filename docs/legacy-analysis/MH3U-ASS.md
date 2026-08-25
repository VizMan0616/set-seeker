# MH3U-ASS — MH 3 Ultimate (gen 3), v1.43b

Upstream: https://github.com/AthenaADP/MH3U-ASS @ `add230fa` — MIT (AthenaADP 2017).
Source root: `sources/MH3U-ASS/`. Solution: `MH3G ASS.sln` / `MH3G ASS.vcproj` (VS2008-era,
`Version="9.00"`).

## Structure

- C++/CLI WinForms, .NET 3.5 (`TargetFrameworkVersion="196613"`).
- ~9,761 LOC. Heaviest files: `Form1.h` (~2,668), `CharmDatabase.cpp` (~1,233, hardcoded charm
  tables), `Solution.cpp` (~1,061).
- Other files: `frmAdvanced.h`, `ManageCharms.h`, `Armor.cpp`, `Common.cpp`, `Skill.cpp`,
  `Decoration.cpp`, `LoadedData.cpp`.
- Data: external under `Athena's ASS MH3G/Data/`.

## Search algorithm

Worker: `Form1.h` `backgroundWorker1_DoWork` (**2114–2201**). Validation:
`Solution::MatchesQuery` (`Solution.cpp:767-836`). Prefilter:
`LoadedData::GetRelevantData` (`LoadedData.cpp:139-185`).

1. **Query** (`FormulateQuery`, `Form1.h:1373-1407`): HR, village★, gender, hunter type,
   weapon slots, **charm table index**, skill combos.
2. **Relevance pruning**: mark requested abilities; collect decorations granting them
   (`GetRelevantDecorations`, `LoadedData.cpp:113-129`); per slot keep armors matching filters
   and not strictly dominated (`AddToList`/`IsBetterThan`, `LoadedData.cpp:72-111`).
3. **Charm fan-out** (`StartSearch`, `Form1.h:1520-1623`): one worker per charm template
   (none / my charms / slot-only / 1-skill / 2-skill via `CharmDatabase::GetCharms`).
4. **5 nested loops** over pruned head×body×arms×waist×legs (`Form1.h:2138-2198`); empty lists
   get a `nullptr` "empty piece".
5. Per combo: allocate `Solution`, copy charm template, `MatchesQuery` — `GetInitialData`
   (armor + charm + weapon slots, Torso Inc), greedy `CalculateDecorations`
   (`Solution.cpp:433-512`), threshold check, optional bad-skill fix, charm reduction.
6. Up to `Environment::ProcessorCount` workers concurrently (`StartTasks`, `Form1.h:1504-1518`).

Complexity: O(|H|·|B|·|A|·|W|·|L|·C) with C charm templates; greedy decoration work O(D·P) per
combo. Dominance pruning only — no mid-tree branch-and-bound.

## Performance problems

| Issue | Location |
|---|---|
| 5-deep nested loops over all pruned pieces | `Form1.h:2138-2198` |
| One worker per charm → many full cartesian products | `QueueTask` 1464–1491, `StartSearch` 1563–1616 |
| `gcnew Solution()` per combo | `Form1.h:2168-2174` |
| Early-exit on MAX_LIMIT commented out | `Form1.h:2182-2187` |
| Progress only per head×body iteration | `Form1.h:2142-2156` |
| `MessageBox::Show` from worker thread | `Form1.h:2190-2193` |
| Huge result text rebuild (`StringBuilder` ~1024×N) | `UpdateResultString` 1789–1936 |
| Mutex contention on progress/results/charms | `Form1.h:79-82, 1989-2000, 2100-2111` |

## Data storage (`Data/`)

CSV-like `.txt`, comma-separated, `#` comments.

| File | Columns | Loader |
|---|---|---|
| `head/body/arms/waist/legs.txt` | name, gender, type, rarity, slots, HR, village★, def, max def, fire/water/ice/thunder/dragon, 5×(skill,pts), 4×(mat,qty), ping, optional `jEvent` | `Armor::Load` (`Armor.cpp:35-126`) |
| `skills.txt` | **leading index columns**, then name, ability, points, type, tags | `Skill::Load` (`Skill.cpp:90+`) |
| `decorations.txt` | name, rarity, slots, HR, village★, skill1+pts, skill2+pts, craft A×4, craft B×4, ping | `Decoration::Load` (`Decoration.cpp:8-89`) |
| `components.txt` | id/index, material name | `Material::LoadMaterials` |
| `tags.txt` | one skill-filter tag per line | `SkillTag::Load` |
| `mycharms.txt` | `NumSlots,Skill1,Points1,Skill2,Points2` | `CharmDatabase::LoadCustom` (184+) |

~330 armor rows/slot, ~196 decorations, ~239 skill rows.

**Charm RNG tables are hardcoded in C++** (`CharmDatabase.cpp`, `StaticData::skill1_table`
from ~284) — no charm CSVs in this repo. Our ETL must extract these arrays into data
(see `docs/specs/data-pack-spec.md`).

## Talismans — full MH3U charm-table modeling

- UI `cmbCharmTable`: Unknown / tables 1–17 / Any (`Form1.h:817-818, 1384`).
- Table seeds: `{1,15,5,13,4,3,9,12,26,18,163,401,6,2,489,802,1203}`
  (`GenerateCharmTable`, `CharmDatabase.cpp:979`).
- Modes (`StartSearch` 1563–1616): no charms; my charms (optimal subset); slot-only gated by
  `have_slots[table,type]`; generated 1-skill/2-skill via `GetCharms`
  (`CharmDatabase.cpp:116-162`).
- Custom charms persisted to `Data/mycharms.txt`; non-custom charms get
  ReduceSlots/ReduceSkills/ReduceCharm after a hit.

## Decorations

Greedy larger-sockets-first; body jewels get the torso multiplier; detrimental second skills
avoided unless allowed (`AddDecorations1`/`AddDecorations23`, `Solution.cpp:295-431`).
Post-pass rearrange/swap (`FixBadSkills`, `RearrangeDecorations`).

## Results UI

RichTextBox dump, display cap `MAX_LIMIT` (default 1000, menu "Max Results",
`Form1.h:1789-1803, 1917-1919`), no pagination, Ctrl+F find. Sort via `cmbSort`
(`SortResults` 2431+): resists, def, max def, difficulty, rarity, spare slots, family, extra
skills. Charm filter combo (`charm_solution_map`/`cmbCharms`).

## Rewrite notes

- The 17 charm tables are the community-datamined MH3U charm RNG; the **table selection**
  concept (user knows their table from in-game sniping) must survive in our game pack as a
  filter over legal charms.
- Skill file format differs from MH4+ (leading index columns) — ETL needs per-game column maps.
