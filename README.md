# set-seeker

Web-based armor set search for classic Monster Hunter (Freedom Unite through Generations
Ultimate). Inspired by Athena's Armor Set Search; AGPLv3 with upstream MIT attribution
in `NOTICE`.

**Now shipping:** Monster Hunter Freedom Unite. Next pack: Portable 3rd (`docs/roadmap.md`).

## Run locally

```bash
# restore the MHFU reference clone first (see SOURCES.md)
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
python -m app.etl --pack mhfu
uvicorn app.main:create_app --factory --reload
```

Or: `docker build . && docker run -p 8000:8000 <image>`.

## For agents

Start at `AGENTS.md`. Domain language and hard constraints: `CONTEXT.md`.
Do not use Tailwind. Do not modify `sources/`.
