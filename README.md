# set-seeker

[![ci](https://github.com/VizMan0616/set-seeker/actions/workflows/ci.yml/badge.svg)](https://github.com/VizMan0616/set-seeker/actions/workflows/ci.yml)
[![license: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)

Web-based armor set search for classic Monster Hunter — from Freedom Unite through
Generations Ultimate. Enter desired skills; get complete armor sets (pieces, decorations,
and talisman where applicable) that activate those skills.

**Now shipping:** [Monster Hunter Freedom Unite](packs/mhfu/) and
[Monster Hunter Portable 3rd](packs/mhp3/). See [docs/roadmap.md](docs/roadmap.md)
for upcoming generations.

## About

set-seeker reimplements the purpose of **Athena's Armor Set Search (ASS)** — the
long-standing Windows tool for building armor sets in pre-World Monster Hunter — as
a cross-platform web application.

Compared to the legacy desktop tool, set-seeker aims to:

- Run in any modern browser (desktop and mobile)
- Stay responsive during search (CP-SAT constraint solver instead of brute-force loops)
- Stream results with pagination instead of dumping everything into one text box
- Deploy simply with Docker

The search engine is **not** a line-by-line port of the legacy C++/CLI code. It models
armor set search as a constraint-satisfaction problem (Google OR-Tools CP-SAT) while
matching legacy behavior where validated against known queries.

## Acknowledgements & inspiration

set-seeker would not exist without **Athena's Armor Set Search**, created by
**AthenaADP** and published under the MIT License. That project was the reference
implementation for armor set building in classic Monster Hunter for many years.

Upstream ASS repositories (MIT, AthenaADP):

- [MHFU-ASS](https://github.com/AthenaADP/MHFU-ASS)
- [MHP3-ASS](https://github.com/AthenaADP/MHP3-ASS)
- [MH3U-ASS](https://github.com/AthenaADP/MH3U-ASS)
- [MH4-ASS](https://github.com/AthenaADP/MH4-ASS)
- [MH4U-ASS](https://github.com/AthenaADP/MH4U-ASS)
- [MHGen-ASS](https://github.com/AthenaADP/MHGen-ASS)
- [MHGU-ASS](https://github.com/AthenaADP/MHGU-ASS)

Game data in this repository is derived from those projects. Each vendored pack carries
attribution under `packs/<pack_id>/vendor/NOTICE`. Full legal detail is in [NOTICE](NOTICE).

MHP3 English display names use the Team Maverick One overlay (`packs/mhp3/vendor/locales/en/`).

**Monster Hunter** is a trademark of Capcom. This is an unofficial fan-made tool, not
affiliated with or endorsed by Capcom.

set-seeker itself is licensed under the [GNU Affero General Public License v3.0](LICENSE).

## Prerequisites

| Path | Requirements |
|------|----------------|
| **Docker** (recommended) | Docker Engine 24+ and Docker Compose v2 |
| **Local development** | Python 3.12+, git |
| **Production** (optional) | VPS with Docker; Traefik overlay — see [docker/README.md](docker/README.md) |

No Athena source clones are required to run the app — game data is vendored under
`packs/*/vendor/`.

## Installation

### Docker (recommended)

```bash
docker compose up --build
```

Open http://localhost:8000. On first boot, bootstrap runs database migrations and ETL
(game data load may take a minute). User data (sessions, charm inventories) persists in
the `setseeker-data` volume across restarts.

### Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
python -m app.bootstrap    # migrate + load packs into data/setseeker.db
uvicorn app.main:create_app --factory --reload
```

Open http://localhost:8000. The SQLite database file is created at `data/setseeker.db`
(relative to the repo root when using the default `DATABASE_URL` in `.env.example`).

### Dev with auto-reload (Docker)

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Configuration

Copy `.env.example` to `.env` at the **project root** (used by compose and local runs):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite path (default dev) or MariaDB DSN (production) |
| `SOLVER_TIME_LIMIT_MS` | Per-solve CP-SAT wall clock |
| `SOLVER_NUM_WORKERS` | CP-SAT worker threads |
| `SETSEEKER_VERSION` | Shown in page footer (set automatically in production deploys) |
| `MARIADB_*` | MariaDB container credentials (see `.env.example`) |
| `RELEASE_ROOT` | Production release tree path for bind mounts |

**MariaDB (production or local test):** use the `prod` image target via
`docker-compose.mariadb.yml` — see [docker/README.md](docker/README.md)
and [ADR 0014](docs/adr/0014-optional-mariadb-compose-profile.md).

**Bind-mount model:** the Docker image installs Python dependencies only. Code, packs,
and migrations are bind-mounted from the repo:

- After editing `app/`, `packs/`, or `alembic/` → `docker compose restart set-seeker`
- After changing `pyproject.toml` dependencies → `docker compose build`

## Usage

1. Open the home page and select a **game** (MHFU or MHP3).
2. Set **desired skills**, hunter type, and progression filters (village ★ / guild rank).
3. Click **Search** — results stream in; use **Load more** for additional sets.
4. For MHP3, register **charm inventories** so searches can use saved talismans.

Domain terms (skill trees, slots, charm tables, etc.) are defined in [CONTEXT.md](CONTEXT.md).

## For contributors

Contributions are welcome! Please read:

- [CONTRIBUTING.md](CONTRIBUTING.md) — setup, tests, pull request flow, **Conventional Commits**
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community standards
- [SECURITY.md](SECURITY.md) — reporting vulnerabilities privately

**Report bugs** and **request features** via GitHub issue templates (linked from the
New Issue page). Complete reports are accepted faster — see CONTRIBUTING for required fields.

**Release cadence:** production updates are **batched**, not deployed per merged PR.
Patch releases ship weekly (Tuesdays); minor (feature) releases monthly; critical hotfixes
can ship immediately. Details in [CONTRIBUTING.md § Release cadence](CONTRIBUTING.md#release-cadence).

**AI / agent contributors:** start at [AGENTS.md](AGENTS.md).

## Development

```bash
ruff check .
ruff format --check .
pytest
```

| Path | Contents |
|------|----------|
| `app/` | FastAPI application, templates, search engine |
| `packs/` | Game data manifests and vendored CSV/TXT |
| `tests/` | Unit, ETL, engine, and web tests |
| `docs/` | Specs, ADRs, legacy analysis, roadmap |

| Document | When to read |
|----------|--------------|
| [CONTEXT.md](CONTEXT.md) | Domain language and hard constraints |
| [docs/specs/engine-spec.md](docs/specs/engine-spec.md) | Search engine behavior |
| [docs/roadmap.md](docs/roadmap.md) | Planned game packs and phases |
| [docs/adr/](docs/adr/) | Architecture decisions |

Maintainers refreshing vendored data from upstream ASS: [SOURCES.md](SOURCES.md) and
`scripts/vendor_pack_data.py`.

## Deployment (maintainers)

Public production uses an optional **Traefik + blue-green** compose overlay
([ADR 0015](docs/adr/0015-production-blue-green-compose.md)):

- Releases are tagged (`vX.Y.Z`); deploy runs **only** on GitHub Release publish — no cron
  or scheduled pull on the server
- If the runner or VPS was offline during a release, GitHub queues the deploy job; for
  catch-up run the **Deploy** workflow manually (latest tag) or `scripts/deploy_latest_release.sh`
- HTTP-first (`http://<VPS-IP>/`) until a domain and TLS are configured
- Zero-downtime: new version starts in the inactive slot, passes `/health`, then Traefik
  switches traffic

Full operations guide: [docker/README.md](docker/README.md).

## License

set-seeker is [AGPL-3.0](LICENSE). Upstream game data and algorithms are attributed under
MIT in [NOTICE](NOTICE). See [SOURCES.md](SOURCES.md) for upstream repository references.
