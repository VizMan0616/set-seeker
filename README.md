# set-seeker

Web-based armor set search for classic Monster Hunter (Freedom Unite through Generations
Ultimate). Inspired by Athena's Armor Set Search; AGPLv3 with upstream MIT attribution
in `NOTICE`.

**Now shipping:** Monster Hunter Freedom Unite and Portable 3rd. Next pack: MHGU
(`docs/roadmap.md`).

## Run with Docker (recommended)

```bash
docker compose up --build
```

Open http://localhost:8000. Game data loads on first boot; user data (sessions,
charm inventories) persists in the `setseeker-data` volume across redeploys.

The Docker **image** installs Python dependencies only. Application code, pack
data, Alembic migrations, and config are **bind-mounted** from the repo — after
editing those trees, restart the container instead of rebuilding:

```bash
docker compose restart set-seeker
```

Rebuild the image only when `pyproject.toml` dependencies change:

```bash
docker compose build
```

For auto-reload while editing `app/`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Copy `config/.env.example` to `config/.env` to override settings.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
python -m app.bootstrap    # migrate + load all packs into data/setseeker.db
uvicorn app.main:create_app --factory --reload
```

No Athena source clones are required — game data is vendored under `packs/*/vendor/`.
Maintainers refreshing from upstream: see `SOURCES.md` and `scripts/vendor_pack_data.py`.

## For agents

Start at `AGENTS.md`. Domain language and hard constraints: `CONTEXT.md`.
Do not use Tailwind. Do not modify `sources/`.
