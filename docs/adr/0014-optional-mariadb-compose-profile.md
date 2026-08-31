# ADR 0014: Optional MariaDB compose profile (deferred production path)

- Status: accepted
- Date: 2026-08-31
- Related: ADR 0004, ADR 0013

## Context

ADR 0004 chose SQLite with a repository layer so MariaDB could replace it via
`DATABASE_URL` alone. ADR 0013 moved game-data loading to runtime bootstrap on a
persistent volume. For production hosting, a dedicated MariaDB instance may be
preferable to a single SQLite file on a volume (concurrency, backups, tooling).

The hard constraint in CONTEXT.md remains: **simple default deploy** — one app
container, no required external services.

## Decision

Provide an **optional** Docker Compose overlay `docker-compose.mariadb.yml` that adds
a MariaDB service and points the app at `mysql+pymysql://…`. Default `docker compose up`
keeps SQLite on a named volume.

Usage: `docker compose -f docker-compose.yml -f docker-compose.mariadb.yml up --build`

Bootstrap (`app/bootstrap.py`) and ETL are unchanged: same Alembic migrations
and pack loads against whichever URL is configured.

## Consequences

- Default path stays one-container + SQLite volume (ADR 0001 friendly).
- Production operators opt in with the MariaDB compose overlay (see above).
- Requires `pip install '.[mariadb]'` (`pymysql`) in the app image when using MariaDB.
- Not activated until a production host is chosen; profile ships as documentation
  and compose stub only.
