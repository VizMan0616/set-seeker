#!/bin/sh
set -eu

# Bootstrap schema + game data, then exec the app server.
python -m app.bootstrap
exec "$@"
