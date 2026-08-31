# What lives in the image vs bind mounts
#
# IN IMAGE (rebuild when pyproject.toml changes):
#   - Python runtime dependencies
#   - docker/entrypoint.sh
#
# BIND-MOUNTED (docker compose restart after edits):
#   - app/          application code, Jinja templates, static assets
#   - packs/        vendored game data + manifests (ETL/bootstrap input)
#   - alembic/      schema migrations
#   - alembic.ini
#   - config/       .env and deployment settings
#
# NAMED VOLUME (persists across restarts and image rebuilds):
#   - /data         SQLite database (game + user data)
