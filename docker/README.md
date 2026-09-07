# Docker deployment

## Images

The `Dockerfile` builds two dependency-only runtime targets (ADR 0013):

| Target | Use | Database driver |
|--------|-----|-----------------|
| `dev` | Local development (`docker-compose.yml`) | SQLite |
| `prod` | Production + MariaDB overlay | SQLite URL still works; image includes `pymysql` |

Application code, packs, and Alembic migrations are **bind-mounted**, not baked into
the image. Rebuild only when `pyproject.toml` dependencies change.

## Configuration

All environment variables live in **`.env` at the project root** (copy from
`.env.example`). Compose reads it for `${VAR}` substitution and passes it to
containers via `env_file`. Local `uvicorn` / `python -m app.bootstrap` also read
`.env` through pydantic-settings (`app/config.py`).

Do not duplicate variables in compose files — set them once in `.env`.

## Compose file layout

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base app service (`dev` image, SQLite) |
| `docker-compose.dev.yml` | Uvicorn `--reload` overlay |
| `docker-compose.mariadb.yml` | MariaDB service + `prod` image for the app |
| `docker-compose.traefik.yml` | Traefik edge proxy (port 80) |
| `docker-compose.prod.yml` | Blue/green app slots |

Stack files independently:

```bash
# Dev + SQLite (default)
docker compose up --build

# Dev + MariaDB (local MariaDB smoke test)
docker compose -f docker-compose.yml -f docker-compose.mariadb.yml up --build

# Production (Traefik + MariaDB + blue/green)
docker compose \
  -f docker-compose.yml \
  -f docker-compose.traefik.yml \
  -f docker-compose.mariadb.yml \
  -f docker-compose.prod.yml \
  up -d
```

---

## What happens on container start

Every app container runs bootstrap before Uvicorn (`docker/entrypoint.sh` →
`python -m app.bootstrap`):

1. **Alembic migrations** — creates/updates all tables.
2. **Conditional ETL** — loads `packs/mhfu` and `packs/mhp3` when the database is
   empty or a pack's `data_version` increased.

User data (sessions, charm inventories) is never touched by ETL. The same bootstrap
runs against SQLite or MariaDB depending on `DATABASE_URL` in `.env`.

---

## Development (SQLite)

```bash
cp .env.example .env
# DATABASE_URL=sqlite:////data/setseeker.db  (already set for Docker)

docker compose up --build
curl -sf http://localhost:8000/health
```

With auto-reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

After editing bind-mounted trees: `docker compose restart set-seeker`.

---

## Local MariaDB smoke test

```bash
cp .env.example .env
```

Edit `.env` (set `MARIADB_*` only — compose builds `DATABASE_URL` from these):

```dotenv
MARIADB_ROOT_PASSWORD=setseeker
MARIADB_PASSWORD=setseeker
MARIADB_USER=setseeker
MARIADB_DATABASE=setseeker
```

Start:

```bash
docker compose -f docker-compose.yml -f docker-compose.mariadb.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.mariadb.yml logs -f set-seeker
```

Expect in logs:

```
[bootstrap] database: mysql+pymysql://setseeker:…@mariadb:3306/setseeker
[bootstrap] empty database — loading all packs
```

Verify data:

```bash
docker exec set-seeker-mariadb mariadb -usetseeker -psetseeker setseeker \
  -e "SELECT code, name FROM games;"
```

---

## Production VPS (Traefik + MariaDB + blue/green)

### Architecture

```
                    ┌─────────────┐
   HTTP :80 ───────►│   Traefik   │
                    └──────┬──────┘
                           │ labels (active slot only)
              ┌────────────┴────────────┐
              ▼                         ▼
     ┌─────────────────┐     ┌─────────────────┐
     │ set-seeker-blue │     │set-seeker-green │
     │  (prod image)   │     │  (prod image)   │
     └────────┬────────┘     └────────┬────────┘
              │                       │
              └───────────┬───────────┘
                          ▼
                 ┌─────────────────┐
                 │    MariaDB      │
                 │  (shared DB)    │
                 └─────────────────┘
```

Traefik, MariaDB, and the app slots are **separate compose overlays** so you can
manage infrastructure lifecycle independently from app deploys.

### Server layout

```
/opt/set-seeker/
  .env                          # production secrets (not in git)
  releases/v0.1.0/              # immutable copy per release tag
  releases/v0.1.1/
  state/active_slot             # "blue" or "green"
  state/deployed_tag            # e.g. v0.1.1
```

### One-time setup

1. Install Docker Engine and Compose v2.
2. Register a GitHub Actions **self-hosted runner** with label `set-seeker`.
3. Clone this repository (or let the deploy workflow manage `releases/` trees).
4. Copy `.env.example` to `.env` at the deploy root and configure:

   ```dotenv
   MARIADB_ROOT_PASSWORD=STRONG_ROOT_PASSWORD
   MARIADB_PASSWORD=STRONG_PASSWORD
   MARIADB_USER=setseeker
   MARIADB_DATABASE=setseeker
   SETSEEKER_VERSION=v0.1.0
   RELEASE_ROOT=/opt/set-seeker/releases/v0.1.0
   ```

   Compose derives `DATABASE_URL` from `MARIADB_*` — do not set a separate MySQL URL.

5. Start infrastructure (Traefik + MariaDB — rarely restarted):

   ```bash
   export RELEASE_ROOT=/opt/set-seeker/releases/v0.1.0
   docker compose \
     -f docker-compose.yml \
     -f docker-compose.traefik.yml \
     -f docker-compose.mariadb.yml \
     up -d traefik mariadb
   ```

6. Publish GitHub Release `v0.1.0` — the deploy workflow runs
   `scripts/deploy_release.sh`.

Set `SETSEEKER_DEPLOY_ROOT=/opt/set-seeker` if the runner checkout lives elsewhere.

### Manual production start (first app slot)

```bash
export RELEASE_ROOT=/opt/set-seeker/releases/v0.1.0

docker compose \
  -f docker-compose.yml \
  -f docker-compose.traefik.yml \
  -f docker-compose.mariadb.yml \
  -f docker-compose.prod.yml \
  up -d traefik mariadb set-seeker-blue
```

Only one app slot should run at a time — stop the other if present:

```bash
docker compose … stop set-seeker-green
```

Open `http://<VPS-public-IP>/`.

### Deploy triggers

Production deploy runs **only** when a GitHub Release is published.

| Event | Action |
|-------|--------|
| Release published | `.github/workflows/deploy.yml` → `scripts/deploy_release.sh` |
| Weekly/monthly release-gate cron | Merges the Release PR — **does not deploy** |
| Runner offline during release | GitHub queues the deploy job |
| Missed deploys | Deploy workflow (`workflow_dispatch`) or `scripts/deploy_latest_release.sh` |

The deploy script merges all four production compose files, ensures Traefik and
MariaDB are up, starts the inactive slot, health-checks it, then switches Traefik
labels.

### HTTP-first (no domain yet)

Traefik listens on **port 80 only**. Static config: `docker/traefik/traefik.yml`.

### Adding TLS when a domain is ready

1. Point DNS `A` record at the VPS.
2. Add `websecure` entrypoint + ACME to `docker/traefik/traefik.yml` (see below).
3. Uncomment port `443:443` on the `traefik` service in `docker-compose.traefik.yml`.
4. Mount an `acme.json` volume for certificate storage.
5. Change router rules from `PathPrefix('/')` to `Host('your.domain')` on the active slot.

Blue-green deploy logic is unchanged.

Example TLS addition to `docker/traefik/traefik.yml`:

```yaml
entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

certificatesResolvers:
  letsencrypt:
    acme:
      email: you@example.com
      storage: /acme/acme.json
      httpChallenge:
        entryPoint: web
```

---

## External / managed MariaDB

If MariaDB runs outside Docker (managed service or host install), omit
`docker-compose.mariadb.yml` and point `DATABASE_URL` in `.env` at the remote host.
The database must exist and the user must have DDL privileges. Bootstrap still runs
migrations + ETL on first app start.

Use the `prod` image target so `pymysql` is available.

---

## Environment variables reference

All are defined in `.env.example`. Key groups:

### Application (`app/config.py`)

| Variable | Default (example) | Purpose |
|----------|-------------------|---------|
| `DATABASE_URL` | `sqlite:////data/setseeker.db` | Database connection |
| `SOLVER_TIME_LIMIT_MS` | `2000` | Per-solve CP-SAT wall clock |
| `SOLVER_NUM_WORKERS` | `8` | OR-Tools threads per solve |
| `SOLVER_MAX_INFLIGHT` | `1` | Concurrent solve cap |
| `SOLVER_QUEUE_WAIT_S` | `30.0` | Queue wait before 503 |
| `SETSEEKER_VERSION` | `0.1.0` | Footer version string |

### MariaDB container

| Variable | Purpose |
|----------|---------|
| `MARIADB_ROOT_PASSWORD` | Root password |
| `MARIADB_DATABASE` | Database name (`setseeker`) |
| `MARIADB_USER` | Application user |
| `MARIADB_PASSWORD` | Application password (must match `DATABASE_URL`) |

### Production deploy

| Variable | Purpose |
|----------|---------|
| `RELEASE_ROOT` | Path to tagged release tree for bind mounts |
| `SETSEEKER_DEPLOY_ROOT` | Base path for `releases/` and `state/` |
| `DEPLOY_FORCE` | Set to `1` to redeploy an already-live tag |

Blue/green routing: the deploy script stops the inactive slot. Traefik only
routes to running containers with `traefik.enable=true` (set in compose).

---

## What gets installed in MariaDB on first boot

After the `prod` image starts with a MySQL `DATABASE_URL`:

1. Alembic applies all migrations through `0003_skill_tags_and_dummy`.
2. Empty `games` table → ETL runs for **mhfu** and **mhp3**.
3. Uvicorn serves on port 8000.

Subsequent restarts: migrations are no-ops at head; ETL runs only when a pack's
`data_version` bumps.

---

## Blue/green with MariaDB

Both slots share one MariaDB server (correct for production). Unlike SQLite on a
shared volume, there is no file-lock contention.

Rules (ADR 0015):

- Only the **incoming** slot runs bootstrap before taking traffic.
- Migrations must stay **expand-only** while blue-green is active.

The `setseeker-data` volume (SQLite path `/data`) is still mounted but unused when
`DATABASE_URL` points at MariaDB.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `ModuleNotFoundError: No module named 'pymysql'` | App not built with `target: prod` — add `docker-compose.mariadb.yml` |
| `Access denied for user 'setseeker'… (1045)` | Stale `mariadb-data` volume — run `docker compose … down -v` and start again |
| Traefik 404 / no backend | App slot has `traefik.enable=false` (old deploy) — recreate with `--force-recreate`; ensure only the active slot is running |
| Traefik logs `client version 1.24 is too old` | Docker Engine 29+ vs Traefik &lt; v3.6.1 — upgrade image to `traefik:v3.6.1` (see `docker-compose.traefik.yml`) |
| App cannot reach MariaDB | Missing `docker-compose.mariadb.yml` or slots not on `setseeker-public` network |
| `set-seeker-blue` fails health check | Check logs: `docker compose … logs set-seeker-blue` — bootstrap/ETL errors |
| Empty game picker | Bootstrap did not finish — verify `games` table has rows |

---

## Quick reference

```bash
# Dev SQLite
cp .env.example .env && docker compose up --build

# Dev MariaDB
# (set DATABASE_URL to mysql+pymysql://… in .env first)
docker compose -f docker-compose.yml -f docker-compose.mariadb.yml up --build

# Production stack (all overlays)
docker compose \
  -f docker-compose.yml \
  -f docker-compose.traefik.yml \
  -f docker-compose.mariadb.yml \
  -f docker-compose.prod.yml \
  up -d
```

See [ADR 0013](../docs/adr/0013-volume-mounted-database.md),
[ADR 0014](../docs/adr/0014-optional-mariadb-compose-profile.md), and
[ADR 0015](../docs/adr/0015-production-blue-green-compose.md).
