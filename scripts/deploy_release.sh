#!/usr/bin/env bash
# Blue-green deploy for set-seeker production (ADR 0015).
#
# Usage: deploy_release.sh <tag>   e.g. deploy_release.sh v0.1.1
#
# Environment:
#   SETSEEKER_DEPLOY_ROOT  Base path (default: parent of repo /opt layout)
#   GITHUB_WORKSPACE       Used when invoked from GitHub Actions checkout

set -euo pipefail

TAG="${1:?Usage: deploy_release.sh <tag>}"
VERSION="${TAG#v}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKOUT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_ROOT="${SETSEEKER_DEPLOY_ROOT:-$CHECKOUT_ROOT}"
STATE_DIR="$DEPLOY_ROOT/state"
STATE_FILE="$STATE_DIR/active_slot"
DEPLOYED_TAG_FILE="$STATE_DIR/deployed_tag"
RELEASE_DIR="$DEPLOY_ROOT/releases/$TAG"

mkdir -p "$STATE_DIR" "$DEPLOY_ROOT/releases"

if [[ -f "$DEPLOYED_TAG_FILE" ]] && [[ "$(cat "$DEPLOYED_TAG_FILE")" == "$TAG" ]] \
  && [[ "${DEPLOY_FORCE:-0}" != "1" ]]; then
  echo "Already deployed $TAG — nothing to do (set DEPLOY_FORCE=1 to redeploy)."
  exit 0
fi

if [[ ! -d "$RELEASE_DIR" ]]; then
  echo "Staging release $TAG -> $RELEASE_DIR"
  rsync -a --delete \
    --exclude releases \
    --exclude state \
    --exclude .git \
    "$CHECKOUT_ROOT/" "$RELEASE_DIR/"
fi

export RELEASE_ROOT="$RELEASE_DIR"
export SETSEEKER_VERSION="$TAG"

ACTIVE="$(cat "$STATE_FILE" 2>/dev/null || echo blue)"
if [[ "$ACTIVE" == "blue" ]]; then
  INACTIVE=green
else
  INACTIVE=blue
fi

compose() {
  docker compose \
    -f "$RELEASE_DIR/docker-compose.yml" \
    -f "$RELEASE_DIR/docker-compose.prod.yml" \
    "$@"
}

echo "Active slot: $ACTIVE — deploying $TAG to inactive slot: $INACTIVE"

# Ensure Traefik is running (uses current release config).
compose up -d traefik

# Start inactive slot without public traffic.
if [[ "$INACTIVE" == "blue" ]]; then
  export TRAEFIK_ENABLE_BLUE=false
  export TRAEFIK_ENABLE_GREEN=false
  compose up -d set-seeker-blue
  HEALTH_HOST=set-seeker-blue
else
  export TRAEFIK_ENABLE_BLUE=false
  export TRAEFIK_ENABLE_GREEN=false
  compose up -d set-seeker-green
  HEALTH_HOST=set-seeker-green
fi

echo "Waiting for $HEALTH_HOST /health ..."
ready=0
for _ in $(seq 1 60); do
  if docker run --rm --network setseeker-public curlimages/curl:8.5.0 \
    -sf "http://${HEALTH_HOST}:8000/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" -ne 1 ]]; then
  echo "ERROR: $HEALTH_HOST failed health check" >&2
  compose logs "$HEALTH_HOST" || true
  exit 1
fi

echo "Health check passed — switching Traefik to $INACTIVE"

if [[ "$INACTIVE" == "blue" ]]; then
  export TRAEFIK_ENABLE_BLUE=true
  export TRAEFIK_ENABLE_GREEN=false
else
  export TRAEFIK_ENABLE_BLUE=false
  export TRAEFIK_ENABLE_GREEN=true
fi

compose up -d set-seeker-blue set-seeker-green

if [[ "$ACTIVE" != "$INACTIVE" ]]; then
  echo "Stopping previous slot: set-seeker-$ACTIVE"
  compose stop "set-seeker-$ACTIVE" || true
fi

echo "$INACTIVE" >"$STATE_FILE"
echo "$TAG" >"$DEPLOYED_TAG_FILE"
echo "Deploy complete: $TAG (active slot: $INACTIVE)"
