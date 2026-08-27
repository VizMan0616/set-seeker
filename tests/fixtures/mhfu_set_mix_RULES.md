# MHFU set-mix matching rules (Agent 2)

Source dump: repo-root `mhfu set mix.txt` (community armor builds, mixed
TeamHGG P2G / official-English / forum typos).

Generated fixture: `tests/fixtures/mhfu_set_mix.json`  
Regenerate: `python tests/fixtures/build_mhfu_set_mix.py`  
(requires `sources/MHFU-ASS` at pinned commit `134acee8…` — see `SOURCES.md`).

## How the original file is parsed

1. Section headers `Blademaster Sets` / `Gunner Sets` set `hunter_type`.
2. Records are separated by a line of underscores.
3. First line is the title (`Name - HR9` or `Name HR9`). Optional
   `Post by` / `Posted by` is the author, not a piece.
4. Optional weapon line: `N Slot Weapon`, `N-slot weapon`, `One/Two/Three slot weapon`.
   Gems immediately under it are weapon jewels.
5. Next **five** non-gem, non-prose lines are pieces in Athena slot order:
   head, body, arms, waist, legs. Gem lines (`[Gem 1: Name]`, also the
   broken `[Gem :1 Name` form) attach to the preceding piece.
6. Remaining short lines are awakened skill names. Lines starting with
   `Note:`, `*`, or long prose are notes (ignored).
7. If the weapon line is omitted and there are no weapon gems,
   `weapon_slots` defaults to **0**.

`[No gems]` and `[Gem …: Empty slot]` are not jewels.

Gender duals (`Obituary/Butterfly Anca`) expand to both names; the fixture
keeps the first mapped CSV name as `name_en` and extras in
`alternates_name_en`.

## Alias strategy (mapping confidence)

Canonical `name_en` is the **Athena CSV** name (what ETL stores). This is
already TeamHGG-style for most rows. A mapped `name_en` **must exist in
that slot’s CSV** — aliases that point at a name Athena does not ship
are rejected (not silently kept).

| Source | Role | Confidence |
|---|---|---|
| Exact CSV `name_en` | identity | high |
| `Languages/TeamHGG MHP2ndG/*` positional overlay | P2G fan names | high |
| `Languages/English MHFU/*` positional overlay | official-English | high |
| `packs/mhfu/name_aliases.yaml` | typos, “Shin”=True G-rank, forum names | high unless noted medium |
| `Narga` ↔ `Naruga` | mechanical extra | high |

Overlays are aligned on identical-name anchors (head lists omit Felyne
Piercing; do not naïvely zip English vs CSV). Overlay names that already
exist as CSV names are **not** remapped (avoids the StrongWall/Rigid Wall
swap).

`fully_mapped` means: every piece/jewel/skill name maps **and** Pass A
succeeds (sockets + positive skill points vs the pack). Name-mapped but
infeasible rows are listed under `meta.mapping.dump_illegal` and skipped.

**Known unmapped names (do not silently drop):**

| Mix name | Why |
|---|---|
| `Kirin Hoop Z` | No such piece. CSV/overlays stop at Kirin Hoop / S / X. |
| `Guardian Spirit Raiment X` | No X piece. G-rank is `TruGuardnSpritRaiment` (English Shin), HR is `GuardianSpritRaiment`. Do not guess. |
| `Rapid Fire Jewel` | Not in CSV/overlays. Do not alias to SpeedFire (AutoReload) or SpeedCharge (Focus). |

**Dump-illegal (names map; combo is not legal in Athena):** see
`meta.mapping.dump_illegal` after a rebuild. Typical causes: 3-slot
Hermit/Master/Unsheathe jewels on 1–2 slot pieces; claimed skills the
listed gear does not reach (Fate 9/10, Evade Inc 9/10, no Artisan).

## What “a pass” means

### Pass A — recorded combination is feasible (no CP-SAT)

Required for every `fully_mapped` row.

Using the MHFU pack (`PackLoader` / ETL DB):

1. Resolve each mapped piece `name_en` in its slot (allow event; do not
   apply hunter-type or HR filters — the dump mixes blade/gunner pieces).
2. Resolve each jewel `name_en`. Per-piece jewel sizes must fit that
   piece’s sockets; weapon jewels must fit `weapon_slots`.
3. Sum skill-tree points: pieces + jewels. **Torso Inc** doubles the body
   piece and jewels socketed in the body.
4. Every mapped **positive** skill (`min_points > 0`) must be met.
   Negative skills in the dump (e.g. Defence −30) are informational.

### Pass B — engine finds *a* set for those skills

Run on a default subset of the hardest `fully_mapped` rows (and on all
of them with `-m mhfu_set_mix_full`). Does not excuse a Pass A failure.

Build a `Query`:

- `skills`: mapped positive skills, at most 5, as
  `SkillRequest(tree_id, min_points)` from the pack
- `weapon_slots` from the record
- `hunter_type` from the record
- `gender`: infer from gendered pieces, else try `"m"` then `"f"`
- `hr` / `village_stars`: **None** (uncapped). Record HR is metadata.
- `allow_event=True`, `allow_bad_skills=True`, `allow_torso_inc=True`

Call `prune` + `solve_one`. Status `optimal` or `feasible`; achieved
points meet every requested tree. Pieces need not match the dump.

## Skips / xfails

- `fully_mapped == false` → `pytest.skip` with `skip_reasons`.
- Unmapped names and dump-illegal combos skip. Do not xfail Pass A on
  `fully_mapped` rows.

## Runtime cap

- Default: Pass A on every row (skips incomplete); Pass B on the **12**
  hardest fully-mapped rows.
- Full Pass B: marker `mhfu_set_mix_full`.

## Invoke (Agent 2)

From repo root, with `sources/MHFU-ASS` present (ETL fixture builds a
scratch DB; do not mutate user tables). Use the project venv:

```bash
.venv/bin/pytest tests/engine/test_mhfu_set_mix.py -m "not mhfu_set_mix_full" -q

.venv/bin/pytest tests/engine/test_mhfu_set_mix.py -m mhfu_set_mix_full -q
```

Do not change positional ETL column maps unless a real CSV parse bug
shows up. Alias table: `packs/mhfu/name_aliases.yaml`.
