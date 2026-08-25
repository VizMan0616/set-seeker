# ADR 0004: SQLite behind a repository layer (MariaDB-ready)

- Status: accepted
- Date: 2026-08-24

## Context

Game data is tiny (≤2.5 MB per game) and read-only at runtime; user data is charm inventories
and search state. Options:

1. **SQLite + build-time ETL**: single file in the image, no services.
2. **CSV/JSON packs in memory**: simplest, but no relational browsing and user data still
   needs a store.
3. **DuckDB**: columnar/analytics — wrong shape for a browsing UI and user writes.
4. **MariaDB in docker-compose**: familiar, but a second container against the
   one-container constraint.

The user accepted SQLite **on the condition** that a future MariaDB swap stays cheap.

## Decision

SQLite, populated by a build-time ETL from the legacy data files. All database access goes
through a repository layer over SQLAlchemy Core with `DATABASE_URL` from config, portable
column types only, and Alembic migrations from day one. The full portability contract and
schema are in `docs/specs/database-schema.md`.

## Consequences

- One-container deployment preserved; game data ships inside the image.
- The solver never hits the database in its hot path (pack data is preloaded to memory), so
  SQLite's write concurrency limits only touch charm-inventory edits — negligible.
- MariaDB swap = set `DATABASE_URL`, run migrations, re-run ETL
  (`docs/specs/database-schema.md` checklist). No code changes if the contract is honored.
- Any SQLite-specific SQL anywhere in the codebase is a contract violation and a review
  blocker.
