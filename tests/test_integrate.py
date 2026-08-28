"""One-image integrate smoke: Docker ships both packs, dual ETL + gates,
picker lists MHP3, one real MHP3 query against the shared DB."""

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.config import get_settings
from app.db import get_engine
from app.domain.models import Query, SkillRequest
from app.engine.pruning import prune
from app.engine.solver import solve_one
from app.main import create_app
from app.pack_loader import PackLoader
from app.repository.game_data import GameDataRepository

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_and_dockerignore_ship_mhp3():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    dockerignore = (REPO_ROOT / ".dockerignore").read_text()
    assert "COPY sources/MHFU-ASS" in dockerfile
    assert "COPY sources/MHP3-ASS" in dockerfile
    assert "--pack mhfu" in dockerfile
    assert "--pack mhp3" in dockerfile
    assert "!sources/MHFU-ASS" in dockerignore
    assert "!sources/MHP3-ASS" in dockerignore


@pytest.fixture(scope="module")
def dual_pack_db(tmp_path_factory):
    """Same sequence as the Dockerfile: mhfu ETL+gate, then mhp3 ETL+gate."""
    db_path = tmp_path_factory.mktemp("integrate") / "setseeker.db"
    url = f"sqlite:///{db_path}"
    for pack in ("mhfu", "mhp3"):
        proc = subprocess.run(
            [sys.executable, "-m", "app.etl", "--pack", pack,
             "--database-url", url],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert "[gate] all checks passed" in proc.stdout
    return url


def test_shared_db_lists_both_games(dual_pack_db):
    repo = GameDataRepository(create_engine(dual_pack_db))
    codes = {row["code"] for row in repo.list_games()}
    assert codes == {"mhfu", "mhp3"}


def test_picker_lists_mhp3(dual_pack_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", dual_pack_db)
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        html = TestClient(create_app()).get("/").text
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()
    assert 'value="mhfu"' in html
    assert 'value="mhp3"' in html
    assert "Monster Hunter Portable 3rd" in html


def test_one_real_mhp3_query(dual_pack_db):
    repo = GameDataRepository(create_engine(dual_pack_db))
    pack = PackLoader(repo)("mhp3")
    trees = {t["name_en"]: t["id"] for t in repo.list_skill_trees(
        repo.get_game_by_code("mhp3")["id"]
    )}
    query = Query(
        game="mhp3",
        skills=(
            SkillRequest(trees["Attack"], 20),
            SkillRequest(trees["Sharpness"], 10),
        ),
        weapon_slots=0,
        gender="m",
        hunter_type="blademaster",
        hr=1,
        village_stars=1,
        use_generated_charms=True,
    )
    outcome = solve_one(
        pack=pack, pruned=prune(pack, query), query=query,
        exclusions=[], time_limit_ms=5000,
    )
    assert outcome.status == "optimal"
    result = outcome.result
    assert result is not None
    assert result.charm_id is not None
    tree_of_skill = {sk.id: sk.tree_id for sk in pack.skills}
    achieved = {
        tree_of_skill[skill_id]: pts for skill_id, pts in result.active_skills
    }
    assert achieved[trees["Attack"]] >= 20
    assert achieved[trees["Sharpness"]] >= 10
