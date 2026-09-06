# Contributing to set-seeker

Thank you for your interest in set-seeker! This document explains how to set up a
development environment, open issues, and submit pull requests.

## Code of conduct

Participation in this project — issues, pull requests, discussions, and reviews — is
governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By contributing, you agree to
uphold it, including our expectation of [Conventional Commits](#conventional-commits)
on pull request titles and commit messages.

## Before you start

1. Read [CONTEXT.md](CONTEXT.md) for domain language and hard constraints (Bootstrap only,
   no Tailwind, no JS build step, one-container Docker default).
2. Check [docs/roadmap.md](docs/roadmap.md) for planned work — open an issue before large
   changes so we can align on scope.
3. Search existing [issues](https://github.com/VizMan0616/set-seeker/issues) to avoid
   duplicate work.

## Development setup

### Docker (recommended)

```bash
docker compose up --build
```

For auto-reload while editing `app/`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### Local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
python -m app.bootstrap
uvicorn app.main:create_app --factory --reload
```

Game data is vendored under `packs/` — no Athena source clones are required.

## Running checks

```bash
ruff check .
ruff format --check .
pytest
```

CI runs the same checks on every pull request. Please run them locally before opening a PR.

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml). A complete report
includes:

- **Game pack** affected (`mhfu`, `mhp3`, …)
- **Steps to reproduce** (search query, UI clicks, or API path)
- **Expected vs actual** behavior
- **Environment** (browser, Docker vs local, version if known)
- **Severity** (cosmetic, functional, blocking)

Incomplete reports may be closed with a request for more detail.

## Requesting features

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.yml). Include:

- The **user problem** (not only your proposed solution)
- Which **game generation(s)** the feature applies to
- **Acceptance criteria** we can test against

Features outside the current [roadmap](docs/roadmap.md) may be labeled `future` rather
than rejected outright.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make focused changes; keep diffs small and readable.
3. Add or update tests when behavior changes.
4. Ensure `ruff check`, `ruff format --check`, and `pytest` pass.
5. Open a PR with a **Conventional Commit** title (see below).
6. Link related issues (`Fixes #123`).

### Repository settings (maintainers)

We use **squash merge** so the PR title becomes the commit on `main`. Branch protection
should require these status checks before merge:

- `ci`
- `conventional-commits`

## Conventional Commits

All pull request titles and commit messages must follow
[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <description>

[optional body]

[optional footer(s)]
```

### Allowed types

| Type | When to use | Release impact |
|------|-------------|----------------|
| `feat` | New user-facing capability | Minor bump (monthly release window) |
| `fix` | Bug fix | Patch bump (weekly release window) |
| `perf` | Performance improvement | Patch bump |
| `refactor` | Code change without behavior change | Patch bump |
| `docs` | Documentation only | Patch bump |
| `test` | Tests only | Patch bump |
| `chore` | Maintenance, CI, deps | Patch bump |

### Examples (matching project history)

```
feat(charms): add talisman inventory to MHP3 search
fix(perf): neg. skill neutralization & charm categories
fix(lang): use TMO's eng translation for game data
perf(engine): prune dead branches earlier
docs: update deployment guide for Traefik
chore(ci): add release-please workflow
```

### Breaking changes

Append `!` after the type/scope or add a `BREAKING CHANGE:` footer. Breaking changes
trigger a **major** version bump and require maintainer review.

```
feat(api)!: remove deprecated search endpoint
```

## Release cadence

Production releases are **batched**, not deployed per merged PR:

| Release type | Schedule | Contents |
|--------------|----------|----------|
| **Patch** | Weekly (Tuesday 14:00 UTC) | Bug fixes, perf, refactors, docs, chores |
| **Minor** | Monthly (1st of month 14:00 UTC) | Features (`feat`) and any queued fixes |
| **Hotfix** | Manual (maintainer dispatch) | Critical outages only — app unusable, data loss |

Merging your PR updates `main` and the standing Release PR changelog; the live site
updates only when a scheduled (or hotfix) release is **published**.

### What triggers production deploy

| Trigger | Deploys? |
|---------|----------|
| GitHub Release **published** | Yes — automatic via self-hosted runner |
| Weekly / monthly release-gate cron | **No** — merges the Release PR only |
| Hotfix release-gate dispatch | **No** — merges the Release PR only |
| Cron, systemd timer, or server task | **Never** — not used for deploy |

There is **no scheduled deploy**. The only automatic path to production is publishing a
GitHub Release.

### Runner or server was offline during a release

GitHub **queues** the deploy workflow while the self-hosted runner is offline. When the
runner reconnects, it picks up the queued job and deploys that release tag.

If several releases published while you were down:

1. **Preferred catch-up:** cancel any stale queued deploy jobs, then run the **Deploy**
   workflow manually (`workflow_dispatch`) with an **empty tag** — it deploys the **latest
   published release** in one step.
2. **On the VPS directly:** `git fetch --tags && scripts/deploy_latest_release.sh`

The deploy script is idempotent: re-running the same tag is a no-op unless
`DEPLOY_FORCE=1`.

### Hotfix policy

Use the hotfix workflow only when the app is **unusable** (500 on `/`, search completely
broken, data loss). Cosmetic bugs and performance regressions wait for the weekly patch
window.

## Project rules for contributors

- **Never modify `sources/`** — upstream clones are reference-only (see `SOURCES.md`).
- **No Tailwind** — Bootstrap only (ADR 0003).
- **No JS build step** — htmx/Alpine via static files.
- **Keep `NOTICE` intact** — preserve AthenaADP MIT attribution.
- **ADRs are settled** — if your change conflicts with `docs/adr/`, open an issue first.

## AI / agent contributors

See [AGENTS.md](AGENTS.md) for task routing and repository skills.

## Security

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md).

## Questions

Open a [GitHub Discussion](https://github.com/VizMan0616/set-seeker/discussions) or an
issue labeled `question` if something is unclear.
