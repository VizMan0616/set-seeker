from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.etl.loaders import load_pack
from app.etl.manifest import load_manifest
from app.etl.writer import PackWriter
from app.repository import tables
from app.repository.game_data import GameDataRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "packs" / "mhfu"


@pytest.fixture(scope="session")
def manifest():
    return load_manifest(PACK_DIR)


@pytest.fixture(scope="session")
def pack_data(manifest):
    return load_pack(manifest)


@pytest.fixture(scope="session")
def etl_db(tmp_path_factory, manifest, pack_data):
    """The MHFU pack loaded once into a scratch SQLite database."""
    db_path = tmp_path_factory.mktemp("etl") / "mhfu.db"
    engine = create_engine(f"sqlite:///{db_path}")
    tables.metadata.create_all(engine)
    repo = GameDataRepository(engine)
    counts = PackWriter(repo).rebuild_pack(manifest, pack_data)
    game_id = repo.get_game_by_code("mhfu")["id"]
    return repo, game_id, counts
