# syntax=docker/dockerfile:1

# set-seeker — dependency-only runtime images (ADR 0013).
#
#   target dev  — SQLite local development (default compose)
#   target prod — MariaDB production (+ pymysql optional extra)
#
# Rebuild when pyproject.toml dependencies change.

FROM python:3.12-slim AS runtime-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/setseeker

WORKDIR /srv/setseeker

RUN useradd --create-home --uid 1000 setseeker \
    && mkdir -p /data /srv/setseeker \
    && chown setseeker:setseeker /data /srv/setseeker

COPY pyproject.toml ./

FROM runtime-base AS dev

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

FROM runtime-base AS prod

RUN python - <<'PY'
import subprocess
import tomllib
from pathlib import Path

project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
deps = list(project["dependencies"]) + list(project["optional-dependencies"]["mariadb"])
subprocess.check_call(["pip", "install", "--no-cache-dir", *deps])
PY

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER setseeker

EXPOSE 8000
ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
