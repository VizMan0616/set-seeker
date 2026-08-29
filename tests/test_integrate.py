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
    assert '"has_dummy": false' in html or '"has_dummy":false' in html
    # MHFU dummy pieces exist; MHP3 catalog must not claim them.
    import json
    import re
    raw = re.search(r'id="ss-catalogs">(.+?)</script>', html, re.S)
    catalogs = json.loads(raw.group(1))
    assert catalogs["mhfu"]["has_dummy"] is True
    assert catalogs["mhp3"]["has_dummy"] is False
    assert catalogs["mhfu"]["torso_inc_name"] == "Torso Inc"
    assert catalogs["mhp3"]["torso_inc_name"] == "Torso Up"
    assert "Allow Torso Inc" in html


def test_stale_mhfu_search_url_follows_game_picker(dual_pack_db, monkeypatch):
    """htmx used to keep POSTing /games/mhfu/search after switching packs."""
    monkeypatch.setenv("DATABASE_URL", dual_pack_db)
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        client = TestClient(create_app())
        repo = GameDataRepository(create_engine(dual_pack_db))
        game = repo.get_game_by_code("mhp3")
        skill = next(
            s for s in repo.list_skills_for_game(game["id"])
            if s["name_en"] == "Attack Up (S)"
        )
        response = client.post(
            "/games/mhfu/search",
            data={
                "game": "mhp3",
                "skill_id": [str(skill["id"])],
                "weapon_slots": "0",
                "gender": "f",
                "hunter_type": "blademaster",
                "hr": "",
                "village_stars": "",
                "sort": "defense",
                "allow_torso_inc": "on",
            },
        )
        assert response.status_code == 200
        assert "Skill is not in this game" not in response.text
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()


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
        charm_mode="two_skill",
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


STRESS_SKILLS = (
    "Water Atk +2",
    "Attack Up (M)",
    "Spirit's Whim",
    "Recovery Up",
    "Divine Blessing",
    "Speed Sharpening",
)


def test_mhp3_six_skill_stress_search_is_not_422(dual_pack_db, monkeypatch):
    """Real 6-skill MHP3 query + typed charm must parse (htmx 422 looks like no results)."""
    monkeypatch.setenv("DATABASE_URL", dual_pack_db)
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        client = TestClient(create_app())
        client.get("/")
        repo = GameDataRepository(create_engine(dual_pack_db))
        game = repo.get_game_by_code("mhp3")
        by_name = {s["name_en"]: s for s in repo.list_skills_for_game(game["id"])}
        trees = {t["name_en"]: t["id"] for t in repo.list_skill_trees(game["id"])}
        ids = [str(by_name[n]["id"]) for n in STRESS_SKILLS]
        added = client.post(
            "/games/mhp3/charms",
            data={
                "slots": "0",
                "skill1_tree": str(trees["Water Atk"]),
                "skill1_points": "5",
                "skill2_tree": str(trees["Attack"]),
                "skill2_points": "9",
            },
            headers={"HX-Request": "true"},
        )
        assert added.status_code == 200
        response = client.post(
            "/games/mhp3/search",
            data={
                "skill_id": ids,
                "weapon_slots": "0",
                "gender": "m",
                "hunter_type": "blademaster",
                "hr": "9",
                "village_stars": "9",
                "sort": "defense",
                "allow_torso_inc": "on",
                "use_generated_charms": "on",
            },
        )
        assert response.status_code == 200
        assert "Invalid" not in response.text
        assert "Choose between" not in response.text
        assert "Skill is not in this game" not in response.text
        assert "ss-empty" in response.text or "ss-result" in response.text
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()
