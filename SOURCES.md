# SOURCES — legacy upstream repositories

The directories under `sources/` are **local-only reference clones** of the six Athena's Armor
Set Search repositories published by AthenaADP on GitHub. They are **not part of this
repository**: `sources/` is gitignored, nothing under it is committed, and a fresh clone of
set-seeker will not contain them. They exist so maintainers can read legacy code during
analysis, cite file:line behavior, and refresh vendored pack data via
`scripts/vendor_pack_data.py` (ADR 0012).

**Runtime and Docker no longer require `sources/`.** Committed game data lives under
`packs/<id>/vendor/`.

All six are licensed **MIT, Copyright (c) 2017 AthenaADP** (see each repo's `LICENSE` once
cloned, and this project's `NOTICE`).

## Restoring the reference clones on a new workstation

Run from the repository root to recreate the exact reference state (pinned commits):

```bash
mkdir -p sources && cd sources
git clone https://github.com/AthenaADP/MHFU-ASS.git  && git -C MHFU-ASS  checkout 134acee87dd0105f3b03dcebe78c5ea9227dafb5
git clone https://github.com/AthenaADP/MHP3-ASS.git  && git -C MHP3-ASS  checkout a22f3ac23e401bd1e1b1df505ebbc5c7590a75b2
git clone https://github.com/AthenaADP/MH3U-ASS.git  && git -C MH3U-ASS  checkout add230fafff114d906455aee9d09007e769517ce
git clone https://github.com/AthenaADP/MH4-ASS.git   && git -C MH4-ASS   checkout e50ea8249645caa4164e089eef62b6b3540e3591
git clone https://github.com/AthenaADP/MH4U-ASS.git  && git -C MH4U-ASS  checkout 4837fe40248eef5fea71a2eeabb31e0fd915ab69
git clone https://github.com/AthenaADP/MHGen-ASS.git && git -C MHGen-ASS checkout 1051ce4da83d565a56a275309a9706869867b3f3
git clone https://github.com/AthenaADP/MHGU-ASS.git  && git -C MHGU-ASS  checkout ae7f125d1d381278d15908d7ce5b092076423918
```

You only need the subset for the generation you are working on (see `docs/roadmap.md`) —
e.g. MHFU-ASS alone when adding or refreshing the MHFU pack. After restoring a clone,
run `python scripts/vendor_pack_data.py <pack_id>` to copy data into `packs/<id>/vendor/`,
then bump `data_version` in the pack manifest and re-run ETL (or `python -m app.bootstrap`).

| Directory | Upstream | Pinned commit | Game / generation | Notes |
|---|---|---|---|---|
| `sources/MHFU-ASS` | https://github.com/AthenaADP/MHFU-ASS | `134acee87dd0105f3b03dcebe78c5ea9227dafb5` (2017-11-28) | MH Freedom Unite (gen 2) | No talismans. Equivalence-class pruning. v3.43b |
| `sources/MHP3-ASS` | https://github.com/AthenaADP/MHP3-ASS | `a22f3ac23e401bd1e1b1df505ebbc5c7590a75b2` (2017-11-26) | MH Portable 3rd (gen 3) | Charms + PSP save import. v1.49b |
| `sources/MH3U-ASS` | https://github.com/AthenaADP/MH3U-ASS | `add230fafff114d906455aee9d09007e769517ce` (2017-11-26) | MH 3 Ultimate (gen 3) | 17 hardcoded charm tables. v1.43b |
| `sources/MH4-ASS` | https://github.com/AthenaADP/MH4-ASS | `e50ea8249645caa4164e089eef62b6b3540e3591` (2017-11-26) | MH 4 (gen 4) | CSV-driven charm generation; excavated gear. v1.06b |
| `sources/MH4U-ASS` | https://github.com/AthenaADP/MH4U-ASS | `4837fe40248eef5fea71a2eeabb31e0fd915ab69` (2017-11-26) | MH 4 Ultimate (gen 4) | 6 charm types; Blowfish save crypto. v1.13b |
| `sources/MHGen-ASS` | https://github.com/AthenaADP/MHGen-ASS | `1051ce4da83d565a56a275309a9706869867b3f3` (2017-11-26) | MH Generations (gen "5-classic") | 3 charm types. v1.10b |
| `sources/MHGU-ASS` | https://github.com/AthenaADP/MHGU-ASS | `ae7f125d1d381278d15908d7ce5b092076423918` (2019-08-18) | MH Generations Ultimate | 4 charm types; Charm Up / Skill +2 mechanics; largest dataset. v1.02b |

## What they are

- **Stack:** C++/CLI (managed C++) Windows Forms, .NET Framework 2.0–4.5 depending on the repo,
  Visual Studio toolsets v90–v141. They are *not* C# projects despite appearances.
- **Data:** external CSV-like `.txt`/`.csv` files under each repo's `Run/Data/` (or equivalent)
  directory — armor per slot, decorations, skills, materials, charm generation tables,
  language overlays. This data is the seed for our ETL (see `docs/specs/data-pack-spec.md`).
- **Engine:** one shared architecture copy-pasted across repos — relevance/dominance pruning,
  then 5–6 nested brute-force loops per charm template, greedy decoration fill.
  See `docs/legacy-analysis/overview.md`.

## Rules

- Do not modify, reformat, or "clean up" anything under `sources/`.
- Never commit anything under `sources/` — the directory is gitignored on purpose. The pinned
  commits above are the provenance record; the restore commands above are the setup step.
- If `sources/` is absent (fresh clone), analysis docs under `docs/legacy-analysis/` remain
  the authoritative summary — they were written against the pinned commits and carry
  file:line citations. Restore the clones when you need to verify or extend them.
- When citing legacy behavior, cite `sources/<REPO>/<path>:<line>`.
