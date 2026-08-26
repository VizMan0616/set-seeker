"""ETL CLI: `python -m app.etl --pack mhfu [--database-url URL] [--skip-gate]`.

Runs Alembic migrations (schema is migration-owned, never ad-hoc DDL —
database-schema.md rule 4), rebuilds the pack's game-data tables via the
repository, then runs the pack's known-query validation gate. A failed gate
exits non-zero: do not ship data that fails it.
"""

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.etl")
    parser.add_argument("--pack", required=True, help="pack id, e.g. mhfu")
    parser.add_argument("--database-url", default=None,
                        help="override DATABASE_URL (default: app config)")
    parser.add_argument("--skip-gate", action="store_true",
                        help="load data without running the validation gate")
    args = parser.parse_args(argv)

    if args.database_url:
        # Must be set before app.config.get_settings() is first called
        # (it is lru_cached, and alembic/env.py reads it).
        os.environ["DATABASE_URL"] = args.database_url

    from alembic.config import Config

    from alembic import command
    from app.config import get_settings
    from app.db import create_engine_from_settings
    from app.etl.gate import run_gate
    from app.etl.loaders import load_pack
    from app.etl.manifest import load_manifest
    from app.etl.writer import PackWriter
    from app.repository.game_data import GameDataRepository

    pack_dir = REPO_ROOT / "packs" / args.pack
    manifest = load_manifest(pack_dir)

    alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(alembic_cfg, "head")

    settings = get_settings()
    engine = create_engine_from_settings(settings)
    repo = GameDataRepository(engine)

    print(f"[etl] loading pack {manifest.id!r} from {manifest.source_data_path}")
    data = load_pack(manifest)
    if data.duplicates_skipped:
        print(f"[etl] skipped legacy (name, gender) duplicates: "
              f"{sorted(set(data.duplicates_skipped))}")

    counts = PackWriter(repo).rebuild_pack(manifest, data)
    print(f"[etl] database: {settings.DATABASE_URL}")
    for table, count in counts.items():
        print(f"[etl]   {table}: {count}")

    if args.skip_gate:
        print("[etl] validation gate skipped")
        return 0

    game = repo.get_game_by_code(manifest.id)
    passed, results = run_gate(repo, game["id"], pack_dir)
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        line = f"[gate] {status} {result.name}"
        if result.detail:
            line += f" — {result.detail}"
        print(line)
    if not passed:
        print("[gate] FAILED — the build is not valid", file=sys.stderr)
        return 1
    print("[gate] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
