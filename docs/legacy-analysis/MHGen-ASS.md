# MHGen-ASS — MH Generations / MHX (gen "5-classic"), v1.10b

Upstream: https://github.com/AthenaADP/MHGen-ASS @ `1051ce4d` — MIT (AthenaADP 2017).
Source root: `sources/MHGen-ASS/`. `GAMES L"MHX and MHGen"`. Same stack as MH4U (v141,
Win 8.1 SDK).

## Structure

- C++/CLI WinForms, ~13.2k LOC.
- Heaviest: `Form1.h` (~3,315), `CharmDatabase.cpp` (~1,300), `Solution.cpp` (~1,289).
- **No** excavated weapons/armor path in `LoadedData` (dropped vs MH4U); save import via
  `SaveData.*` (not the Blowfish `Crypto/` of MH4U).
- Data: ~1.5 MB; ~620–676 armor rows/slot; 219 decorations; 269 skills; **3 charm types**
  (mystery, shining, ancient).

## Search algorithm

Same shared engine: `StartSearch` / `backgroundWorker1_DoWork` (`Form1.h:~2627+`),
`LoadedData::GetRelevantData` (~243–319), `Solution::MatchesQuery` (`Solution.cpp:~967-1059`).

Pipeline identical to MH4U minus the weapon loop and excavated gear: query → relevance +
dominance prune → one worker per charm template → 5 nested armor loops → per-combo greedy
decoration fill → threshold check → optional fixes. Results hash-deduped,
`MaxSolutions = 100000`.

## Performance problems

Same family as MH4U: 5-deep loops (`Form1.h:~2653+`), one worker per charm, per-combo
`gcnew Solution`, full decoration recompute per combo, head×body-only progress, RichTextBox
monolithic dump (`UpdateResultString`), commented-out `MAX_LIMIT` early exit, cooperative
cancel.

## Data storage (`Run/Data/`)

Core files as in MH4/4U (armor per slot, decorations, skills without leading index columns,
compound_skills, components, tags, `Languages/*/`). Charm CSVs for the 3 types under
`Run/Data/Charm Generation/`. User charms in `Data/mycharms.txt`.

## Talismans

Same dual model (user charms + CSV-driven procedural tables). `GetCharms(query, twoSkill)` at
`CharmDatabase.cpp:~1184`. Three charm types only. UI modes identical (`cmbCharmSelect`).

## Decorations

Greedy 3→2→1 with torso multiplier; bad-skill fixing via 1-slot swaps; Advanced Search
overrides. Same as MH4U.

## Results UI

RichTextBox dump, `MAX_LIMIT` display cap (default 1000), 100k ingest cap, sort combo, charm
and extra-skill filters, no pagination.

## Rewrite notes

- Closest sibling to MHGU with a smaller dataset — a good "intermediate" pack when validating
  the gen-5-classic ETL before MHGU's ~2× data volume.
- Demonstrates the feature-flag pattern: same engine as MH4U with `excavated_gear: false` and
  `weapon_search: false`.
