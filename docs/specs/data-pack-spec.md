# Data pack spec — legacy data formats and ETL mapping

A **game pack** is one generation's data + feature flags. ETL reads vendored raw files under
`packs/<id>/vendor/` (ADR 0012) and writes the normalized SQLite schema
(`docs/specs/database-schema.md`). Game data is **read-only at runtime**; bootstrap loads it
on first boot or when `data_version` increases (ADR 0013).

## Pack manifest

Each pack has a manifest (YAML) declaring flags, vendored paths, and provenance:

```yaml
id: mhfu
name: "Monster Hunter Freedom Unite"
generation: 2
data_version: 1                    # bump when vendor/ files change
data:
  armor_dir: vendor/data           # relative to pack_dir
  locale_overlays:
    en: vendor/locales/en
provenance:
  upstream: AthenaADP/MHFU-ASS
  commit: 134acee87dd0105f3b03dcebe78c5ea9227dafb5
  license: MIT
features:
  talismans: false
  # … see existing flag matrix below
progression:
  guild_rank: 9
  village_stars: 9
formats:
  armor_file_ext: csv
  armor_header_lines: 2
  skills_leading_index_columns: 0
locales: [en, ja]
desired_skills_max: 5
```

ETL stores `data_version` in `games.features` alongside feature flags. Bootstrap compares
manifest vs installed version to decide whether to re-run ETL for that pack.

ETL copies `desired_skills_max` onto `games.features`. The search UI and query
parser read that field — **do not hardcode 5** and do not `if game == …`.

Athena has **no** add/subtract for desired skills. `NumSkills` is a compile-time
count of combo boxes:

| Pack | `desired_skills_max` | Athena |
|---|---|---|
| mhfu | 5 | `sources/MHFU-ASS/MH Armor/Form1.h:85` |
| mhp3 | 6 | `sources/MHP3-ASS/Form1.h:95` |
| mh3u | 6 | `sources/MH3U-ASS/Form1.h:78` |
| mh4 | 6 | `sources/MH4-ASS/Form1.h:80` |
| mh4u | 7 | `sources/MH4U-ASS/Form1.h:89` |
| mhgen | 7 | `sources/MHGen-ASS/Form1.h:87` |
| mhgu | 7 | `sources/MHGU-ASS/Form1.h:87` |

Talisman packs declare inventory point steppers (`charm_points`). Do not share
±13 across skill 1 and skill 2. ETL **overwrites** those keys with the union of
all `charm_generation/*_skill1.csv` / `*_skill2.csv` envelopes (same bounds for
every tree — no per-skill gift list). MHP3 union today: skill 1 `1…10`, skill 2
`−10…13`. Athena `ManageCharms.h` `CreateCharm` is a similar wide clamp
(`0…10` / `−10…13`), not per-tree truncation. Generated search charms still
use the per-type CSV envelopes, not this union.

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

Progression ceilings are **Athena quest-star numbers** (`nudHR` / `nudElder` on
`Form1.h`), not in-game Hunter Rank (HR 1–999). Copy them into
`progression.guild_rank` / `progression.village_stars`. ETL writes
`guild_rank_max` / `village_stars_max` onto `games.features`; the search UI
offers Uncapped plus 1…cap. Do not re-scan armor files for the cap — data uses a
**sentinel** (10 in MHFU, 99 later) for “not via this path.”

| Pack | Village ★ | Guild / HR | Athena UI | Notes |
|---|---|---|---|---|
| mhfu | 9 | 9 | `Form1.h:540,593` | G-rank Unite; sentinel 10 |
| mhp3 | 6 | 6 | `Form1.h:655,708` | High-rank only |
| mh3u | 10 | 8 | `Form1.h:764,856` | Village 10★; hub through G-rank ★8 |
| mh4 | 7 | 8 | `Form1.h:803,856` | High-rank only; hub ★8 (not 7) |
| mh4u | 10 | 12 | `Form1.h:1491,1504` | G-rank is hub ★9–12 (G1–G4); `GetTier` treats `hr > 8` as G |
| mhgen | 6 | 8 | `Form1.h:1076,1090` | High-rank only |
| mhgu | 10 | 13 | `Form1.h:1090,1104` | G-rank hub ★9–13 |

Do not share one global max. Base games and expansions in the same generation
differ (MH4 8/7 vs MH4U 12/10; MHGen 8/6 vs MHGU 13/10).

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
- `Languages/*/` — localized name overlays applied at ETL from `vendor/locales/en/`.
  For MHFU, **`name_en` is the official Freedom Unite English pack** (formerly
  `Languages/English MHFU/`), not the CSV strings (those match TeamHGG's P2G fan
  translation). For MHP3, **`name_en` is Team Maverick One** (formerly
  `Languages/English (TMO)/`); CSV English stays Athena/TeamHGG and is used only as
  parse keys and overlay fallback. Japanese `name_ja` is always the Athena CSV Japanese
  column. Dummy pieces are flagged from overlay names that contain `(dummy)`; the marker
  is not stored in `name_en`.
- `mycharms.txt` — **not** ETL'd; it is user data. Our equivalent lives in the `user_charms`
  table (same logical shape: `slots, skill1, points1, skill2, points2`).

## ETL rules

1. **Per-pack column maps.** Never share positional parsing across packs; each manifest
   declares its format quirks (header lines, index columns, slot notation).
2. **Names are bilingual from day one** (`name_en`, `name_ja`). For MHFU, `name_en` comes
   from `vendor/locales/en` (official localization). For MHP3, `name_en` comes from the
   same path (Team Maverick One fan pack). A blank overlay row falls back to the CSV
   English string and is counted. MHP3 stays `translation: fan` (see `docs/adr/0009`).
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
