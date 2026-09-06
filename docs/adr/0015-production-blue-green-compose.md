# ADR 0015: Optional production blue-green compose profile

- Status: accepted
- Date: 2026-09-06
- Related: ADR 0001 (one-container default), ADR 0013 (bind mounts), ADR 0014 (optional overlays)

## Context

The default `docker-compose.yml` runs a single `set-seeker` service on port 8000.
That is ideal for local development and simple self-hosting.

Production requirements added:

1. **Zero-downtime deploys** — start a new version, verify health, then switch traffic.
2. **Automatic deploy on release** — self-hosted GitHub Actions runner on the VPS.
3. **HTTP-first edge routing** — Traefik on port 80 before a domain/TLS is available.

ADR 0001 mandates one app container for the default deploy. ADR 0014 established
precedent for optional compose overlays (MariaDB) that are not required for the
simple path.

## Decision

Add an **optional production overlay** (`docker-compose.prod.yml`) used only on
the public VPS:

- **Traefik** — edge reverse proxy (port 80 initially; TLS added when a domain exists).
- **Two app slots** — `set-seeker-blue` and `set-seeker-green`, sharing the
  `setseeker-data` volume (SQLite user + game data per ADR 0013).
- **Blue-green switch** — `scripts/deploy_release.sh` starts the inactive slot,
  polls `/health`, toggles Traefik labels, stops the old slot.
- **Immutable release trees** — each deploy copies the tagged checkout to
  `releases/vX.Y.Z/`; bind mounts point at that path.

Local development and the default README path remain **unchanged** — single
container, no Traefik.

## Consequences

- Production VPS runs three containers (Traefik + one active app slot; inactive
  only during deploy). Default one-container constraint preserved for dev/simple deploy.
- SQLite migrations must stay **expand-only** while blue-green runs — only the
  incoming slot runs `app.bootstrap` before taking traffic.
- Traefik requires Docker socket access on the host (standard for Docker provider).
- TLS is a config-only follow-up: add `websecure` entrypoint + ACME to
  `docker/traefik/traefik.yml` when a domain is registered.
- Deploy workflow targets a self-hosted runner labeled `set-seeker`.
- **Deploy is release-only:** publishing a GitHub Release triggers deploy. No cron,
  systemd timer, or VPS background task deploys code. Weekly/monthly cron workflows
  merge Release PRs only.
- If the runner or server was offline during a release, GitHub queues the deploy job;
  manual catch-up: Deploy workflow (`workflow_dispatch`, empty tag) or
  `scripts/deploy_latest_release.sh`.

## Alternatives considered

- **Caddy** — viable; Traefik chosen for Docker-native service discovery and
  label-based blue-green toggling.
- **Weekly pull of `main`** — rejected; releases are tag-bound and cadence-gated
  (see CONTRIBUTING.md).
- **Single-container rolling restart** — simpler but brief downtime during bootstrap.
