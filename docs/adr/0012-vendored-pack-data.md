# ADR 0012: Vendored pack data (no runtime dependency on Athena clones)

- Status: accepted
- Date: 2026-08-31
- Supersedes: the build-time `sources/` COPY workflow described in early
  `data-pack-spec.md` drafts and the Dockerfile before ADR 0013

## Context

Game data originally lived in six Athena's ASS repositories under `sources/`,
gitignored locally. The Docker build copied `sources/MHFU-ASS` and
`sources/MHP3-ASS` and ran ETL at image build time. Every fresh clone or CI run
that lacked those clones could not build or load data.

Submodules were rejected: we need the data files, not the C++/CLI codebase.
MHP3 charm generation already committed extracted CSV facts under
`packs/mhp3/charm_generation/` (data-pack-spec.md).

## Decision

Each game pack vendors the raw files ETL reads into `packs/<id>/vendor/`:

- `vendor/data/` — armor, skills, decorations (formerly `Run/Data`)
- `vendor/locales/en/` — English name overlay (formerly `Languages/…`)

The pack manifest declares `data.armor_dir`, `data.locale_overlays`, `data_version`,
and `provenance` (upstream repo, pinned commit, license). ETL reads only
pack-local paths; `sources/` remains gitignored and **maintainer-only** for
legacy analysis and running `scripts/vendor_pack_data.py` when refreshing data.

## Consequences

- `git clone` + `docker compose up` works without Athena clones.
- Upstream MIT attribution lives in per-pack `vendor/NOTICE` and manifest
  `provenance`.
- Refreshing from a new Athena commit: bump pinned commit in manifest, run the
  vendor script, bump `data_version`, re-run ETL (bootstrap picks it up).
- Repo size grows with raw data (~low MB per pack today; MHGU is the future
  stress test).
