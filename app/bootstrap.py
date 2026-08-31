"""Database bootstrap: Alembic migrations + conditional ETL seed/refresh.

Used by docker/entrypoint.sh and `python -m app.bootstrap`. Never touches
user tables — only schema migrations and idempotent game-data reloads.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.db import create_engine_from_settings
from app.etl.manifest import PackManifest, list_pack_dirs, load_manifest
from app.repository.game_data import GameDataRepository

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_migrations() -> None:
    alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(alembic_cfg, "head")


def _installed_data_version(repo: GameDataRepository, manifest: PackManifest) -> int | None:
    game = repo.get_game_by_code(manifest.id)
    if game is None:
        return None
    features = json.loads(game["features"])
    version = features.get("data_version")
    return int(version) if version is not None else None


def pack_needs_etl(repo: GameDataRepository, manifest: PackManifest) -> bool:
    """True when the pack is missing or its vendored data_version is newer."""
    installed = _installed_data_version(repo, manifest)
    if installed is None:
        return True
    return manifest.data_version > installed


def run_etl_pack(pack_id: str, *, skip_gate: bool = False) -> int:
    """Run the ETL CLI for one pack. Returns process exit code."""
    from app.etl.__main__ import main as etl_main

    argv = ["--pack", pack_id]
    if skip_gate:
        argv.append("--skip-gate")
    return etl_main(argv)


def bootstrap(*, skip_gate: bool = False) -> int:
    """Migrate schema, then seed or refresh game data as needed."""
    settings = get_settings()
    print(f"[bootstrap] database: {settings.DATABASE_URL}")

    run_migrations()
    engine = create_engine_from_settings(settings)
    repo = GameDataRepository(engine)

    packs = [load_manifest(d) for d in list_pack_dirs()]
    if not packs:
        print("[bootstrap] no packs found under packs/", file=sys.stderr)
        return 1

    empty = not repo.list_games()
    if empty:
        print("[bootstrap] empty database — loading all packs")
        for manifest in packs:
            code = run_etl_pack(manifest.id, skip_gate=skip_gate)
            if code != 0:
                return code
        return 0

    for manifest in packs:
        if pack_needs_etl(repo, manifest):
            installed = _installed_data_version(repo, manifest)
            if installed is None:
                print(f"[bootstrap] seeding pack {manifest.id!r}")
            else:
                print(
                    f"[bootstrap] refreshing pack {manifest.id!r} "
                    f"(installed data_version={installed}, "
                    f"manifest data_version={manifest.data_version})"
                )
            code = run_etl_pack(manifest.id, skip_gate=skip_gate)
            if code != 0:
                return code
        else:
            print(f"[bootstrap] pack {manifest.id!r} up to date")

    return 0


def main(argv: list[str] | None = None) -> int:
    return bootstrap()


if __name__ == "__main__":
    raise SystemExit(main())
