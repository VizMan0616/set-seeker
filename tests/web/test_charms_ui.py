"""One web path that exercises pack flag talismans (Advanced + inventory)."""

import json

from fastapi.testclient import TestClient

from app.main import create_app
from tests.web.test_search_ui import SEARCH_FORM


def test_talismans_flag_inventory_and_advanced_tab(packed_db):
    packed_db.create_game(
        id=2, code="mhp3", name="Monster Hunter Portable 3rd",
        generation=3,
        features=json.dumps({
            "talismans": True, "guild_rank_max": 6, "village_stars_max": 6,
        }),
    )
    packed_db.create_skill_tree(
        id=10, game_id=2, name_en="Attack", name_ja="Attack",
        category_tag="Offensive",
    )
    packed_db.create_skill(
        id=10, tree_id=10, name_en="Attack Up (S)", points=10,
    )
    for slot in range(5):
        packed_db.create_armor_piece(
            id=200 + slot, game_id=2, slot=slot,
            name_en=f"P3 Slot {slot}", rarity=1, slots=0,
            gender=2, hunter_type=2, defense=1, max_defense=1,
            res_fire=0, res_water=0, res_ice=0, res_thunder=0, res_dragon=0,
        )
        packed_db.set_armor_skill(armor_id=200 + slot, tree_id=10, points=3)
    kind = packed_db.create_charm_type(game_id=2, code="mystery", max_slots=3)
    packed_db.set_charm_skill_range(
        charm_type_id=kind["id"], tree_id=10, skill_slot=1,
        min_points=0, max_points=4,
    )
    packed_db.set_charm_slot_threshold(
        charm_type_id=kind["id"], fulfillment=0, slots=0,
    )
    packed_db.set_charm_slot_threshold(
        charm_type_id=kind["id"], fulfillment=1, slots=1,
    )
    packed_db.set_charm_slot_threshold(
        charm_type_id=kind["id"], fulfillment=10, slots=0,
    )

    client = TestClient(create_app())

    home = client.get("/")
    assert home.status_code == 200
    assert 'name="charm_mode"' in home.text
    assert 'value="one_skill"' in home.text
    assert "Use legal generated charms" not in home.text
    assert "Use my charms" not in home.text

    assert client.get("/games/mhfu/charms").status_code == 404

    inventory = client.get("/games/mhp3/charms")
    assert inventory.status_code == 200
    assert "Add a charm" in inventory.text
    assert "My talismans" in inventory.text

    added = client.post(
        "/games/mhp3/charms",
        data={"slots": "1", "skill1_tree": "10", "skill1_points": "4", "skill2_tree": ""},
        follow_redirects=True,
    )
    assert added.status_code == 200
    assert "Attack +4" in added.text

    search = client.post(
        "/games/mhp3/search",
        data={**SEARCH_FORM, "skill_id": ["10", "", "", "", ""]},
    )
    assert search.status_code == 200
    assert 'data-adv-tab="charms"' in search.text
    assert "Charms" in search.text
    assert 'name="rel_charm_id"' in search.text
    assert "Attack +1" in search.text
    assert "Attack +5" not in search.text
    assert "Attack +4 OOO" not in search.text
    assert "Attack +4 OO-" not in search.text
