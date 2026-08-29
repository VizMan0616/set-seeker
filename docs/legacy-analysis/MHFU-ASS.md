# MHFU-ASS — MH Freedom Unite (gen 2), v3.43b

Upstream: https://github.com/AthenaADP/MHFU-ASS @ `134acee8` — MIT (AthenaADP 2017).
Source root: `sources/MHFU-ASS/`. Solution: `MH Armor.sln`, project `MH Armor/MH Armor.vcxproj`.

## Structure

- C++/CLI WinForms, .NET ~2.0 (`TargetFrameworkVersion="131072"`), VS2017 toolset v141.
- ~5,400 LOC of `.cpp`/`.h`. `Form1.h` alone ~1,792 lines.
- Key files: `MH Armor/Form1.h` (UI + search orchestration), `Solution.cpp/.h` (equivalence
  matching, decoration fill), `LoadedData.cpp` (load/filter), `Armor.cpp`, `Decoration.cpp`,
  `Skill.cpp` (models + CSV parsers), `GGGThread.h` (Win32 thread helper), `frmAdvanced.h`.
- Data: external under `Run/Data/`, not embedded.
- Progression caps (Athena `nudHR` / `nudElder`): **guild HR 9, village ★9**
  (`Form1.h:540,593`). Armor sentinel for a closed path is 10.

## Search algorithm

Worker: `Form1.h` `backgroundWorker1_DoWork` (~1334–1431). Matching:
`Solution.cpp` `EquivalenceSolution::MatchesQuery` (~121–150). Prep:
`Query::CreateEquivalences` (~89–119), `LoadedData::GetRelevantData` (~199–244).

1. **Query** (`FormulateQuery` ~992–1027): up to **5** skills (`NumSkills` at
   `MH Armor/Form1.h:85` — five static combo boxes, no add/subtract), HR/village★, gender,
   blade/gunner, weapon slots, flags (piercings, dummy, torso Inc, bad skills).
2. **Relevance + dominance prune** (`GetRelevantData`/`AddToList`): keep armors/decorations
   helping query skills or with max slots; drop strictly dominated pieces (`Armor::IsBetterThan`).
3. **Equivalence classes** (`CreateEquivalences`): group armors with identical slots + relevant
   skill vector into `ArmorEquivalence` — unique to MHFU, cuts the search space.
4. **Parallelize by head class**: one `BackgroundWorker` per head equivalence
   (`StartSearch` ~1057–1058).
5. **Brute-force nest** over body × arms × waist × legs equivalences (~1353–1379).
6. Per combo, `MatchesQuery`: sum skill points (Torso Inc doubles body), add weapon slots,
   **greedy decoration fill** 3→2→1 (`CalculateDecorations` ~161–238) with torso-slot
   preference and a small scoring heuristic (`GetScore` ~310–318).
7. On match, expand equivalences to concrete pieces (nested loops ~1390–1418), then
   `CheckBadSkills` / optional gem reorder.

Complexity: workers ≈ E_h head classes; each O(E_b·E_a·E_w·E_l) matches, then O(product of
class sizes) expansion per hit. Worst case O(n⁵) over filtered pieces; decoration fill is
greedy O(D) per candidate, not an exact jewel knapsack.

## Performance problems

| Issue | Location | Impact |
|---|---|---|
| 4-deep equivalence loops + 5-deep expansion loops | `Form1.h:1353-1418` | Combinatorial core cost |
| `gcnew EquivalenceSolution` / `gcnew Solution` per combo | `Form1.h:1381,1400` | GC pressure |
| Progress marshals full solution lists; giant `StringBuilder` into `txtSolutions` | `Form1.h:1325-1332, 1198-1282` | **The visible UI freeze** |
| `CreateEquivalences` on the UI thread pre-search | `Form1.h:1047` | Startup hitch |
| Per-worker cap 1000 but one worker per head class | `Form1.h:84, 1412-1416, 1057-1058` | Total results ≫ 1000 |
| "Showing first 1000" does not truncate the built text | `Form1.h:1271-1278` | Misleading; string still huge |
| Cancel = `CancelAsync`, checked only in the waist loop | `Form1.h:1108-1111, 1374-1378` | Coarse cancellation |
| Dominance prune is O(n²) list scans | `LoadedData.cpp:137-159` | Pre-search cost |

Search runs on BackgroundWorkers; the freeze is from progress UI updates and text rebuilds.

## Data storage (`Run/Data/`)

Loaded by `LoadedData::ImportTextFiles` (`LoadedData.cpp:15-30`).

| File | Columns | Loader |
|---|---|---|
| `head.csv` … `legs.csv` | Header rows: Name, Price, Mat1–4+amounts, Defence, Fire/Thunder/Dragon/Water/Ice Res, Gender, Hunter Type, Rarity, HR, Elder★, Slots (`O--`), Skill1+pts … Skill5+pts | `Armor::Load` (`Armor.cpp:18-92`); skips 2 header lines |
| `decorations.csv` | **No header.** Name, Price, Slots, HR, Elder★, pts1, Ability1, pts2, Ability2, 4×(qty,mat) + 4× alt craft | `Decoration::Load` (`Decoration.cpp:55-108`) |
| `skills.txt` | Ability blocks: `"Ability"` + optional `tag="…"`, then `points "Skill Name"` lines, blank-line separated | `Skill::Load` (`Skill.cpp:64+`) |
| `components.txt` | One material name per line | `Material::LoadMaterials` |
| `Languages/*/` | Localized name lists + `strings.txt` | `LoadedData::LoadLanguage`. CSV names are TeamHGG-style; set-seeker ETL stores **English MHFU** (official) as `name_en`. |

Approx sizes: ~410–428 armor rows per slot, ~167 decorations, ~514 skill lines.

## Talismans

**None.** Gen 2 has no charm type, no charm UI, no charm in `Solution`. Search is
head/body/arms/waist/legs + weapon slots + decorations only. In set-seeker this is the
game-pack feature flag `talismans: false`.

## Decorations

- Loaded into `Decoration::static_decorations` + map by primary ability.
- Filtered to query skills (`GetRelevantDecorations`, `LoadedData.cpp:175-189`).
- Greedy fill preferring 3-slot then 2 then 1; torso slots filled with torso multiplier
  (`Solution.cpp:161-238`).
- Post-match `FixBadSkills`/`ReorderGems` may swap gems to clear negative skills
  (`Solution.cpp:31-87, ~369-378`).
- Dual-skill jewels: secondary points applied; flagged "dangerous" if the secondary hits a
  desired ability.

## Results UI

Single multiline TextBox, no pagination; results streamed during search, sorted and rewritten
on completion. Soft display claim of first 1000 (`MAX_LIMIT`); workers stop at 1000 each.
Sort combo: None / Dragon / Fire / Ice / Thunder / Water / Defence / Difficulty / Rarity /
Slots spare (`SortResults` ~1721–1741). Ctrl+F find dialog; Advanced Search lets the user tick
individual candidate pieces/jewels.

## Rewrite notes

- Smallest dataset and no charm dimension → ideal first vertical slice (see `docs/roadmap.md`).
- The equivalence-class idea survives as "representative per identical (slots, relevant-skill
  vector) group" in the solver model (`docs/specs/engine-spec.md`).
- `AssemblyInfo.cpp` still says "Copyright (c) Microsoft 2009" — template leftover; the MIT
  `LICENSE` at repo root is authoritative.
