# MHP3-ASS — MH Portable 3rd (gen 3), v1.49b

Upstream: https://github.com/AthenaADP/MHP3-ASS @ `a22f3ac2` — MIT (AthenaADP 2017).
Source root: `sources/MHP3-ASS/`. Solution: `Athena's ASS MHP3rd.sln`.

## Structure

- C++/CLI WinForms + native PSP crypto for charm import.
- ~9,800 LOC (`Form1.h` ~2,364; `CharmDatabase.cpp` ~1,166).
- Key files: `Form1.h`, `Solution.cpp`, `CharmDatabase.cpp`, `LoadedData.cpp`, `Armor.cpp`,
  `Decoration.cpp`, `ManageCharms.h`, `ImportCharms.h`, `PSPCryptoEngine.cpp`,
  `SaveDataEncryption.cpp`.
- Data: external `.txt` CSV-like files (not `.csv`) under `Run/Data/`.
- Progression caps (Athena `nudHR` / `nudElder`): **guild HR 6, village ★6**
  (`Form1.h:655,708`). High-rank only; closed-path sentinel in data is 99.

## Search algorithm

Worker: `Form1.h` `backgroundWorker1_DoWork` (~1852–1930). Matching:
`Solution::MatchesQuery` (`Solution.cpp` ~660–724).

1. **Query** (`FormulateQuery` ~1192+): up to 6 skills, HR, village★, gender, type, weapon
   slots, allow event / low rank / bad skills.
2. **Relevance + dominance prune** (`LoadedData.cpp:121-167`). **No equivalence classes**
   (unlike MHFU).
3. **Charm-mode fan-out** (`StartSearch` ~1293–1372): one worker per charm template —
   mode 0: no charm; 1: "My Charms" (+ no-charm pass); 2: 3-slot blank charm; 3: generated
   one-skill charms (`GetCharms(…, false)`); 4: generated two-skill charms (`GetCharms(…, true)`).
4. Each worker: **5 nested loops** over relevant head/body/arms/waist/legs
   (`Form1.h:1874-1926`); empty slot lists get a `nullptr` piece.
5. `MatchesQuery`: init points from armor + charm + weapon slots (`GetInitialData` ~228–269);
   greedy decorations 3→2→1 with Torso Inc (`CalculateDecorations` ~271+); reject if any
   desired skill under target; optional bad-skill fix; for non-custom charms,
   `ReduceSlots`/`ReduceSkills`/`ReduceCharm`/`RearrangeDecorations` minimize the required charm.

Complexity: per charm template O(H·B·A·W·L); modes 3–4 generate many templates → effectively
O(C·n⁵).

## Performance problems

| Issue | Location | Impact |
|---|---|---|
| Full 5-deep armor loops, no equivalence pruning | `Form1.h:1874-1926` | Combinatorial core |
| One worker per charm template | `Form1.h:1307-1369` | Many parallel O(n⁵) jobs |
| **`MAX_LIMIT` early exit commented out** | `Form1.h:1916-1921` | Search always exhausts the space |
| `gcnew Solution` + full `MatchesQuery` per tuple | `Form1.h:1904-1912` | Alloc + greedy deco per combo |
| Startup charm table RNG simulation | `CharmDatabase::GenerateCharmTable` ~901–961 | Heavy launch cost |
| End-of-search dump of huge text; "first 1000" doesn't slice | `Form1.h:1558-1668` | UI freeze on render |
| Weak armor hash for dedup (`index << (i*3)`) | `Form1.h:1691-1698` | Collision risk; null-unsafe |
| `CancelAsync` only | `Form1.h:1468-1475` | Coarse cancellation |

## Data storage (`Run/Data/`)

`LoadedData::ImportTextFiles` (`LoadedData.cpp:26-42`).

| File | Columns | Loader |
|---|---|---|
| `head.txt` … `legs.txt` | `#` comment header: engname, 名前, gender(0/1/2), type(0/1/2), rarity, slots, HR, village★, def, max def, 5 resists, 5×(skill,pts), 4×(mat,qty) | `Armor::Load` (`Armor.cpp:18-103`) |
| `decorations.txt` | eng, jap, rarity, slots, HR, village★, skill1,pts, skill2,pts, 4× craft A, 4× craft B | `Decoration::Load` (`Decoration.cpp:8-80`) |
| `skills.txt` | **no leading index columns** (unlike MH3U): eng-name, Skill(jap), eng-ability, Skill-Tree, Points, Type, tag, order. `#` comment header. Empty ability column = Torso Inc. | `Skill::Load` (`Skill.cpp:64-131`) |
| `tags.txt` | Tag names (Offensive, Defensive, …) | `SkillTag::Load` |
| `components.txt` | Material names | Materials loader |
| `mycharms.txt` | `#Format: NumSlots,Skill1,Points1,Skill2,Points2` | `CharmDatabase::LoadCustom` (~108–168) |
| `Languages/*/` | Localized overlays. set-seeker ETL stores **`English (TMO)`** (Team Maverick One) as `name_en`; CSV columns stay TeamHGG/Athena English as parse keys. Japanese `name_ja` comes from the CSVs. | Language loaders |

Approx: ~210–230 armor rows/slot (~1080 after name-only dedup), 164 decorations, 210
skill data rows (209 thresholds + Torso Inc), ~259 mycharms lines.

## Talismans (central to this game)

`Charm` model: `Armor.h:32-50` — `num_slots` + up to 2 ability pairs; flags `custom`/`hacked`.

Sources:
1. **User charms** — `Data/mycharms.txt` + Manage Charms UI; optional **PSP save import**
   (`ImportCharms.h`, decrypt via `PSPCryptoEngine.cpp`/`SaveDataEncryption.cpp`).
2. **Generated legal charms** — `CharmDatabase::GenerateCharmTable` simulates the in-game charm
   RNG tables into max-point maps; `GetCharms` (`CharmDatabase.cpp:11-86`) picks candidates for
   the query.
3. Search attaches one charm template per worker; matching **reduces** overpowered generated
   charms (`ReduceCharm`, `Solution.cpp:633-658`).

UI: charm select mode + "Filter Results by Charm" combo (`cmbCharms`).

## Decorations

Same greedy 3→2→1 family as MHFU, refined (`AddDecorations1`/`AddDecorations23` templates,
torso vs non-torso lists). `GetBestDecoration` uses a full query scan or pre-bucketed
`rel_decoration_map` by slot size (`Decoration.cpp:104-157`). Event jewels gated by
`allow_event`.

## Results UI

Big TextBox, no pagination. During search: count updates; solutions stored in
`all_solutions`/`no_charm_solutions`/`charm_solution_map`. After finish: charm filter combo;
selecting rebuilds text via `UpdateResultString` (~1558+). Sort: resistances, defence, max
defence, difficulty, rarity, slots spare (`SortResults` ~2149–2172). Soft `MAX_LIMIT = 1000`
message; the search itself no longer stops at 1000.

## Rewrite notes

- MHP3 was never officially localized: English armor/skill names are **fan
  translations** (`translation: fan`, ADR 0009). Display English is Team Maverick
  One from `Languages/English (TMO)/`, not the Athena/TeamHGG CSV strings.
- The PSP save decryption (`PSPCryptoEngine.cpp`) is explicitly out of v1 scope; see
  `docs/adr/0006` and the per-generation deferral note.
- Second vertical slice after MHFU: adds the charm dimension (inventory + generated legal
  charms) to the solver model.
- ETL (2026-08): confirmed armor/decoration slots are **integers**, not `O--`; gender/type
  are Athena `0/1/2` (both/male/female and both/blade/gunner), remapped to schema
  0=male/blade, 1=female/gunner, 2=both. Duplicate armor is **name-only**
  (`ArmorExists`, `Armor.cpp:10-16`) — 26 later gender-twin rows dropped
  (1080 pieces kept). `skills.txt` is tabular with **no leading index columns**
  (unlike MH3U); empty ability column is Torso Inc. Charm RNG tables extracted
  from UTF-16 `CharmDatabase.cpp` (`OmaSkill::SKILL` / `FURUSLO` / `tableinit[12]`)
  into `packs/mhp3/charm_generation/` (mystery / shining / timeworn; tree
  columns keep Athena English and are remapped to TMO at ETL). Closed village
  path uses sentinel 99.
