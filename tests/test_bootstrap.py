"""Bootstrap tests: migrate, seed, and data_version refresh."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.bootstrap import bootstrap, pack_needs_etl
from app.config import get_settings
from app.etl.manifest import load_manifest
from app.repository import tables
from app.repository.game_data import GameDataRepository

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bootstrap_db(tmp_path, monkeypatch):
    db_path = tmp_path / "bootstrap.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    from app.db import get_engine
    get_engine.cache_clear()
    yield url
    get_settings.cache_clear()
    get_engine.cache_clear()


def test_bootstrap_seeds_empty_db(bootstrap_db):
    assert bootstrap() == 0
    engine = create_engine(bootstrap_db)
    repo = GameDataRepository(engine)
    codes = {g["code"] for g in repo.list_games()}
    assert codes == {"mhfu", "mhp3"}
    mhfu = repo.get_game_by_code("mhfu")
    features = json.loads(mhfu["features"])
    assert features["data_version"] == 1


def test_bootstrap_skips_when_up_to_date(bootstrap_db):
    assert bootstrap() == 0
    assert bootstrap() == 0


def test_pack_needs_etl_when_missing(bootstrap_db):
    engine = create_engine(bootstrap_db)
    tables.metadata.create_all(engine)
    repo = GameDataRepository(engine)
    manifest = load_manifest(REPO_ROOT / "packs" / "mhfu")
    assert pack_needs_etl(repo, manifest) is True


def test_etl_all_cli(bootstrap_db):
    proc = subprocess.run(
        [sys.executable, "-m", "app.etl", "--all",
         "--database-url", bootstrap_db],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "[gate] all checks passed" in proc.stdout
