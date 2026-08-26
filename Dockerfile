# syntax=docker/dockerfile:1

# set-seeker — single-container build (CONTEXT.md hard constraint).
# Stage 1 installs dependencies and runs the MHFU data ETL (roadmap Phase 0:
# "multi-stage, ETL at build time, single runtime container"). Stage 2 is the
# runtime: app source (for templates/static), the built SQLite DB, uvicorn.

FROM python:3.12-slim AS build

WORKDIR /build

# Install dependencies (and the project metadata) from pyproject.toml.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# ETL inputs: pack manifest/known queries, Alembic migrations, legacy data.
COPY packs ./packs
COPY alembic ./alembic
COPY alembic.ini ./
COPY sources/MHFU-ASS ./sources/MHFU-ASS

# Build the SQLite game database (migrations + pack load + validation gate;
# the build fails if the gate fails).
RUN mkdir -p /data \
    && python -m app.etl --pack mhfu --database-url sqlite:////data/setseeker.db


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/setseeker.db

RUN useradd --create-home --uid 1000 setseeker

COPY --from=build /usr/local /usr/local
COPY --from=build /build/app /srv/setseeker/app
COPY --from=build --chown=setseeker:setseeker /data/setseeker.db /data/setseeker.db

# The app runs from its source tree so Jinja2 templates and the vendored
# static assets (app/web/...) resolve; PYTHONPATH puts it ahead of the
# site-packages copy installed by pip.
ENV PYTHONPATH=/srv/setseeker

# The runtime DB is writable: sessions and search_states are runtime data.
RUN chown -R setseeker:setseeker /data
USER setseeker

EXPOSE 8000
# --proxy-headers: trust X-Forwarded-Proto/For from a local reverse proxy
# (e.g. cloudflared) so request.url_for and redirects keep the https scheme.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
