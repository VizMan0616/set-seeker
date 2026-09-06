# Docker deployment

## What lives in the image vs bind mounts

**In image** (rebuild when `pyproject.toml` changes):

- Python runtime dependencies
- `docker/entrypoint.sh`

**Bind-mounted** (`docker compose restart` after edits):

- `app/` — application code, Jinja templates, static assets
- `packs/` — vendored game data + manifests (ETL/bootstrap input)
- `alembic/` + `alembic.ini` — schema migrations
- `config/` — `.env` and deployment settings

**Named volume** (persists across restarts and image rebuilds):

- `/data` — SQLite database (game + user data)

See [ADR 0013](../docs/adr/0013-volume-mounted-database.md).

## Default (development and simple self-host)

```bash
docker compose up --build
```

Port 8000 is published directly. User data survives in the `setseeker-data` volume.

## Development overlay (auto-reload)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Uvicorn reloads when files under `app/` change.

## Optional MariaDB overlay

```bash
docker compose -f docker-compose.yml -f docker-compose.mariadb.yml up
```

See [ADR 0014](../docs/adr/0014-optional-mariadb-compose-profile.md).

## Production overlay (Traefik + blue-green)

For the public VPS with zero-downtime deploys. See
[ADR 0015](../docs/adr/0015-production-blue-green-compose.md).

### Components

| Service | Role |
|---------|------|
| `traefik` | Edge reverse proxy on port 80 (TLS added when domain exists) |
| `set-seeker-blue` / `set-seeker-green` | Two app slots; only one receives traffic at a time |
| Shared `setseeker-data` volume | SQLite DB shared across slots |

### First-time VPS setup

1. Install Docker Engine and Compose v2.
2. Register a GitHub Actions **self-hosted runner** with label `set-seeker`.
3. Clone this repository (or let the deploy workflow manage `releases/` trees).
4. Copy `config/.env.example` to `config/.env` and adjust if needed.
5. Publish GitHub Release `v0.1.0` — deploy workflow runs `scripts/deploy_release.sh`.

Recommended layout on the server:

```
/opt/set-seeker/
  releases/v0.1.0/    # immutable copy per tag
  releases/v0.1.1/
  state/active_slot   # "blue" or "green"
  state/deployed_tag  # e.g. v0.1.1 — current live release
```

Set `SETSEEKER_DEPLOY_ROOT=/opt/set-seeker` if the runner checkout lives elsewhere.

### Deploy triggers (no cron)

Production deploy runs **only** when a GitHub Release is published. There is no cron,
systemd timer, or background task on the VPS that pulls or deploys code.

| Event | Action |
|-------|--------|
| Release published | `.github/workflows/deploy.yml` runs on the self-hosted runner |
| Weekly/monthly release-gate cron | Merges the Release PR — **does not deploy** |
| Runner offline during release | GitHub queues the deploy job; it runs when the runner returns |
| Long downtime / missed deploys | Run **Deploy** workflow manually (empty tag → latest release) or `scripts/deploy_latest_release.sh` on the VPS |

### Manual production start (without deploy script)

```bash
export RELEASE_ROOT=/opt/set-seeker/releases/v0.1.0
export SETSEEKER_VERSION=v0.1.0
export TRAEFIK_ENABLE_BLUE=true
export TRAEFIK_ENABLE_GREEN=false

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d traefik set-seeker-blue
```

Open `http://<VPS-public-IP>/`.

### HTTP-first (no domain yet)

Traefik listens on **port 80 only**. No Let's Encrypt until you own a domain pointing
at the VPS.

Static config: `docker/traefik/traefik.yml` — single `web` entrypoint.

### Adding TLS when a domain is ready

1. Point DNS `A` record at the VPS.
2. Add to `docker/traefik/traefik.yml`:

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

3. Uncomment port `443:443` on the `traefik` service in `docker-compose.prod.yml`.
4. Mount an `acme.json` volume for certificate storage.
5. Change router rules from `PathPrefix('/')` to `Host('your.domain')` on the active slot.

Blue-green deploy logic is unchanged — only Traefik static config and router labels update.

### Deploy script

`scripts/deploy_release.sh <tag>` — used by `.github/workflows/deploy.yml`:

1. Skip if `state/deployed_tag` already matches (unless `DEPLOY_FORCE=1`)
2. Stage tagged checkout under `releases/<tag>/`
3. Start inactive slot (no Traefik traffic)
4. Poll `/health` on the internal Docker network
5. Enable Traefik labels on the new slot; disable the old slot
6. Stop the previous slot; persist active slot and deployed tag

**Catch-up after downtime:** `scripts/deploy_latest_release.sh` (fetches tags, deploys
latest `v*`). Same as the Deploy workflow with an empty tag input.

### SQLite and migrations

Only the **incoming** slot runs `app.bootstrap` (Alembic + conditional ETL) before taking
traffic. Migrations must be **expand-only** (add tables/columns; never drop user data).

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:////data/setseeker.db` | Database connection |
| `SETSEEKER_VERSION` | `0.1.0` | Footer version string |
| `RELEASE_ROOT` | `.` | Path to tagged release tree (production) |
| `TRAEFIK_ENABLE_BLUE` | `true` | Route public traffic to blue slot |
| `TRAEFIK_ENABLE_GREEN` | `false` | Route public traffic to green slot |
| `SETSEEKER_DEPLOY_ROOT` | repo root | Base path for `releases/` and `state/` |
| `DEPLOY_FORCE` | `0` | Set to `1` to redeploy an already-live tag |
