import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_engine
from app.main import create_app
from app.repository import tables as t
from app.sessions import SESSION_COOKIE_NAME
from tests.conftest import GAME_ID


def test_app_boots_and_session_middleware_issues_cookie(packed_db):
    client = TestClient(create_app())

    first = client.get("/")
    assert first.status_code == 200
    assert first.cookies.get(SESSION_COOKIE_NAME)

    second = client.get("/")
    assert second.status_code == 200
    # Known session: the cookie is not re-issued.
    assert SESSION_COOKIE_NAME not in second.cookies


def test_app_fails_clearly_when_no_pack_is_loaded(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/empty.db")
    get_settings.cache_clear()
    get_engine.cache_clear()
    with pytest.raises(RuntimeError, match="python -m app.etl"):
        create_app()


def test_bulk_insert_and_delete_game_data(packed_db):
    repo = packed_db
    base_rows = repo.list_armor_pieces(GAME_ID, slot=0, allow_event=True)
    assert len(base_rows) == 3

    def bulk_helm(piece_id: int, name: str) -> dict:
        return {"id": piece_id, "game_id": GAME_ID, "slot": 0, "name_en": name,
                "rarity": 1, "slots": 0, "gender": 2, "hunter_type": 2,
                "hr_required": 0, "village_stars": 0, "defense": 1, "max_defense": 1,
                "res_fire": 0, "res_water": 0, "res_ice": 0, "res_thunder": 0,
                "res_dragon": 0, "torso_inc": False, "is_event": False}

    repo.bulk_insert(t.armor_pieces, [
        bulk_helm(9001, "Bulk Helm A"),
        bulk_helm(9002, "Bulk Helm B"),
    ])
    assert len(repo.list_armor_pieces(GAME_ID, slot=0, allow_event=True)) == 5

    repo.delete_game_data(GAME_ID)
    assert repo.list_armor_pieces(GAME_ID, allow_event=True) == []
    assert repo.list_skill_trees(GAME_ID) == []
    assert repo.list_decorations(GAME_ID, allow_event=True) == []
    # The games row itself survives a pack wipe.
    assert repo.get_game_by_code("mhfu")["id"] == GAME_ID
