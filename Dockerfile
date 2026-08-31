# syntax=docker/dockerfile:1

# set-seeker — dependency-only runtime image (ADR 0013).
#
# The image installs Python packages and the entrypoint only. Mutable project
# trees (app, packs, alembic, config) are bind-mounted by docker-compose.yml
# so code and data changes need `docker compose restart`, not `docker build`.
#
# Rebuild the image when pyproject.toml dependencies change.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/setseeker.db \
    PYTHONPATH=/srv/setseeker

WORKDIR /srv/setseeker

RUN useradd --create-home --uid 1000 setseeker \
    && mkdir -p /data /srv/setseeker \
    && chown setseeker:setseeker /data /srv/setseeker

# Install runtime dependencies from pyproject.toml (no application source copy).
COPY pyproject.toml ./
RUN python - <<'PY'
import subprocess
import tomllib
from pathlib import Path

project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
subprocess.check_call(
    ["pip", "install", "--no-cache-dir", *project["dependencies"]],
)
PY

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER setseeker

EXPOSE 8000
ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
