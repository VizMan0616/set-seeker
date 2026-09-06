#!/usr/bin/env bash
# Deploy the latest semver git tag (manual catch-up when runner/server was offline).
#
# No cron — run this yourself after bringing the VPS or self-hosted runner back, or use
# the "deploy" workflow_dispatch in GitHub Actions (empty tag = latest release).
#
# Usage: deploy_latest_release.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"
git fetch --tags origin

TAG="$(git tag -l 'v*' --sort=-version:refname | head -1)"
if [[ -z "$TAG" ]]; then
  echo "ERROR: no v* tags found after git fetch --tags" >&2
  exit 1
fi

echo "Latest release tag: $TAG"
exec "$SCRIPT_DIR/deploy_release.sh" "$TAG"
