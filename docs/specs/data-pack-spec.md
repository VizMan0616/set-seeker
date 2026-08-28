# Data pack spec — legacy data formats and ETL mapping

A **game pack** is one generation's data + feature flags. Packs are built at Docker image
build time by an ETL step that reads the legacy CSV-like files from `sources/<REPO>/` and
writes the normalized SQLite schema (`docs/specs/database-schema.md`). Game data is
**read-only at runtime**.

## Pack manifest

Each pack has a manifest (YAML/JSON) declaring its flags and source paths:

```yaml
id: mhfu
name: "Monster Hunter Freedom Unite"
generation: 2
source_repo: sources/MHFU-ASS
data_dir: "MH Armor/Run/Data"        # per-repo location of the data files
features:
  talismans: false                    # gen 2 has no charm slot
  charm_tables: false                 # MH3U-style table selection
  charm_generation: false             # gen4+ CSV-driven legal-charm generation
  excavated_gear: false               # MH4/4U relic equipment
  weapon_search: false                # weapons as a 6th search dimension
  charm_up: false                     # MHGU: double charm skills
  skill_plus_two: false               # MHGU: +2 to all trees
  compound_skills: false              # gen4+: one tree grants several others
progression:
  guild_rank: 9                       # HR / guild quest cap (not the ETL sentinel 10)
  village_stars: 9                    # village / Elder★ cap
formats:
  armor_file_ext: csv                 # MHFU uses .csv; all others .txt
  armor_header_lines: 2               # MHFU: 2 header lines; others: comment headers
  skills_leading_index_columns: 0     # MH3U skills.txt has 2 leading index columns
locales: [en, ja]
```

Expected flag matrix (verify against each repo before ETL implementation):

| Pack | talismans | charm_tables | charm_generation | excavated | weapon_search | charm_up | skill+2 | compound |
|---|---|---|---|---|---|---|---|---|
| mhfu | — | — | — | — | — | — | — | — |
| mhp3 | ✓ | ✓ | — | — | — | — | — | — |
| mh3u | ✓ | ✓ (17) | — | — | — | — | — | — |
| mh4 | ✓ | — | ✓ (4 types) | ✓ | ✓ | — | — | ✓ |
| mh4u | ✓ | — | ✓ (6 types) | ✓ | ✓ | — | — | ✓ |
| mhgen | ✓ | — | ✓ (3 types) | — | — | — | — | ✓ |
| mhgu | ✓ | — | ✓ (4 types) | — | — | ✓ | ✓ | ✓ |

Progression ceilings (ETL writes `guild_rank_max` / `village_stars_max` onto
`games.features`; the search UI only offers Uncapped plus 1…cap):

| Pack | Village ★ | Guild / HR | Notes |
|---|---|---|---|
| mhfu | 9 | 9 | G-rank Freedom Unite; 10 is the “not via this path” sentinel |
| mhp3 | (pack) | (pack) | High-rank Portable 3rd — set when adding the pack |
| mh3u | (pack) | (pack) | G-rank 3U — set when adding the pack |
| mh4 | (pack) | 7 typical | High-rank only; confirm in that gen’s ASS |
| mh4u | (pack) | G-rank (confirm G3 vs G4) | Expansion ceiling; confirm in MH4U-ASS |
| mhgen / mhgu | (pack) | (pack) | Set from that pack’s quest tables |

Do not share one global max. Base games and expansions in the same generation
often differ.

## Source file formats (as found in the legacy repos)

### Armor — `head|body|arms|waist|legs.(csv|txt)`

One file per equipment slot. Logical columns (order and extras vary per game — the ETL uses a
per-pack column map, never positional assumptions shared across packs):

`name_en, name_ja, gender (0/1/2), hunter_type (0=blade/1=gun/2=both), rarity, slots (0–3 or "O--"), hr, village_stars, defense, max_defense, res_fire, res_water, res_ice, res_thunder, res_dragon, up to 5×(skill_tree, points), up to 4×(material, qty)`

Per-game parser references: MHFU `Armor.cpp:18-92` (2 header lines, `O--` slot notation);
MHP3 `Armor.cpp:18-103`; MH3U `Armor.cpp:35-126` (trailing ping col, optional `jEvent`);
MH4+/Gen/GU same family without leading index columns.

### Skills — `skills.txt`

Two families:

- **MHFU**: block format — `"Ability"` line (+ optional `tag="…"`), then `points "Skill Name"`
  lines, blank-line separated (`Skill.cpp:64+`).
- **MHP3/MH3U**: rows with **leading index columns** — `idx, idx, name_en, name_ja, ability,
  points, type, tag, order` (MH3U `Skill.cpp:90+`).
- **MH4+**: rows without leading indices — `name, ability, points, type, tags…`
  (MH4 `Skill.cpp:102-117`).

`type` marks normal vs negative (bad) skills. `tags` feed the UI skill filter.

### Decorations — `decorations.(csv|txt)`

`name_en, name_ja, rarity, slots (1–3), hr, village_stars, skill1, points1, skill2, points2,
4× craft materials A, 4× craft materials B`. MHFU's file has **no header**
(`Decoration.cpp:55-108`); MHP3+ have comment headers (`Decoration.cpp:8-80` family).

### Charm generation — `Charm Generation/*.csv` (MH4+ only)

- `{type}_skill1.csv`: `skill_tree, min_points, max_points`
- `{type}_skill2.csv` (all types except mystery): same shape
- `{type}_slots.csv`: `fulfillment_value, slot1_threshold, slot2_threshold, slot3_threshold`

Charm types per pack: mh4 = mystery/shining/ancient/distorted; mh4u = + enduring, graven (6);
mhgen = mystery/shining/ancient (3); mhgu = + enduring (4).
Loader reference: MH4U `CharmDatabase.cpp:~1115-1139`.

### MH3U/MHP3 charm tables (hardcoded — extraction required)

MH3U's 17 charm tables and MHP3's RNG simulation live in C++ arrays
(MH3U `CharmDatabase.cpp` from ~284; seeds at ~979; MHP3 `GenerateCharmTable` ~901–961).
The ETL for these packs includes a one-time **extraction script** that converts the arrays
into the same CSV shape as gen 4+, so runtime code only ever reads one format. The extracted
data is committed to the pack (it is facts/data, MIT-licensed), not re-derived at build time.

### Compound skills — `compound_skills.txt` (gen 4+)

Maps a compound tree to its component trees. ETL expands these so the solver sees plain trees
(legacy behavior: components auto-disable when the compound is present).

### Other files

- `components.txt` — material names (crafting info display).
- `tags.txt` — skill filter categories.
- `Languages/*/` — localized name overlays applied at ETL. For MHFU, **`name_en` is the
  official Freedom Unite English pack** (`Languages/English MHFU/`), not the CSV strings
  (those match TeamHGG's P2G fan translation: "Speed Fire", "All Shots Up", "SpeedFire Jewel").
  Japanese and other locales remain future overlays. Dummy pieces are flagged from overlay
  names that contain `(dummy)`; the marker is not stored in `name_en`.
- `mycharms.txt` — **not** ETL'd; it is user data. Our equivalent lives in the `user_charms`
  table (same logical shape: `slots, skill1, points1, skill2, points2`).

## ETL rules

1. **Per-pack column maps.** Never share positional parsing across packs; each manifest
   declares its format quirks (header lines, index columns, slot notation).
2. **Names are bilingual from day one** (`name_en`, `name_ja`). For MHFU, `name_en` comes
   from `Languages/English MHFU` (official localization). Missing translations fall back
   to the other language with a `translation: fan` marker where applicable (MHP3 English
   names are fan translations — see `docs/adr/0009`).
3. **Skill trees are normalized** into `skill_trees` + `skills` (threshold rows) +
   `armor_skills` / `decoration_skills` junction rows. Never store skill points as packed
   columns in relational tables.
4. **Slots are integers 0–3**; `O--` notation is parsed at ETL.
5. **Resistances and defense** are stored but never used by the solver's hard constraints —
   they are ranking/display data.
6. **Idempotent builds**: the ETL drops and rebuilds game-data tables; user tables
   (`sessions`, `user_charms`) are never touched by ETL.
7. **Validation gate**: after load, run the pack's known-query suite
   (`docs/specs/engine-spec.md` §7) before the image is considered built.
8. **Advanced Search columns** = armor slots + decorations + any true feature flags
   (`talismans` → charms, `weapon_search` → weapons). The ETL must not drop gender-split
   rows or dominated-but-relevant pieces; the engine lists them under `inf`. Advanced does
   not need extra tables — fill `armor_pieces` / `decorations` (and later charm/weapon
   tables) with gender, hunter type, progression, skills, slots, torso Inc, dummy/event.
   If this generation's `MatchesQuery` adds a filter we lack, that is a Query hard-filter
   flag, documented in `docs/legacy-analysis/<GAME>-ASS.md`.

## Known-query validation suite (per pack, to be filled during implementation)

Each pack must ship ≥3 replayable queries with expected results taken from the legacy tool,
e.g. for MHFU: a classic "Attack Up L + Sharpness +1" blademaster set at HR-capped and
uncapped levels. These are the regression oracle for both ETL and solver.
