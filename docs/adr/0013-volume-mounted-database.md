# ADR 0013: Volume-mounted database and runtime bootstrap

- Status: accepted
- Date: 2026-08-31
- Amends: ADR 0004 (consequence "game data ships inside the image" — replaced)

## Context

The original Dockerfile ran ETL in a build stage and copied `/data/setseeker.db`
into the runtime image. Problems:

1. Rebuilding the image after a code-only change recreated the database and
   destroyed user data (sessions, charm inventories).
2. A compose volume at `/data` replaced the baked DB with an empty directory,
   crashing startup.
3. No entrypoint ran Alembic or ETL on first boot.

ADR 0004 chose SQLite with a repository layer; user data and game data already
share one file but are logically separated (ETL never touches user tables).

## Decision

- **Dependency-only image:** Python packages from `pyproject.toml` and
  `docker/entrypoint.sh` only — no application source, packs, Alembic, or config
  baked in. Rebuild when dependencies change; not for every code edit.
- **Bind-mounted project trees** (default `docker-compose.yml`):
  - `app/` — application code, templates, static assets
  - `packs/` — vendored game data, manifests (bootstrap/ETL input)
  - `alembic/` + `alembic.ini` — schema migrations
  - `config/` — `.env` and deployment settings
  Code or pack edits take effect after `docker compose restart set-seeker`.
- **Persistent named volume:** `DATABASE_URL=sqlite:////data/setseeker.db` on
  `setseeker-data` (user sessions, charm inventories, and the SQLite file).
- **Runtime bootstrap:** `docker/entrypoint.sh` runs `python -m app.bootstrap`
  before uvicorn:
  1. `alembic upgrade head` (schema migrations; user rows preserved)
  2. If DB empty → ETL all packs
  3. If `manifest.data_version` > installed `games.features.data_version` →
     ETL that pack only (idempotent game-data rebuild)
- **Dev overlay:** `docker-compose.dev.yml` adds uvicorn `--reload` on `app/`.

The one-container deployment constraint from ADR 0001 is preserved: one app
service, no required external database service.

## Consequences

- Code deploys do not wipe user talismans when the `/data` volume is kept.
- Game-data updates come from the bind-mounted `packs/` tree; bootstrap refreshes
  packs whose `data_version` increased.
- First boot is slower (ETL + validation gates); subsequent starts are fast.
- Deploy host must have the repository checkout present for bind mounts (typical
  for self-hosted or dev); the image alone is not a standalone artifact without
  mounted source trees.
- MariaDB for production remains a config swap (ADR 0004 portability contract);
  see ADR 0014 for an optional compose overlay.
