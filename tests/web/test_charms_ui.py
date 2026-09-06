"""One web path that exercises pack flag talismans (Advanced + inventory)."""

import json

from fastapi.testclient import TestClient

from app.main import create_app
from tests.web.test_search_ui import SEARCH_FORM


def test_talismans_flag_inventory_and_advanced_tab(packed_db):
    packed_db.create_game(
        id=2,
        code="mhp3",
        name="Monster Hunter Portable 3rd",
        generation=3,
        features=json.dumps(
            {
                "talismans": True,
                "guild_rank_max": 6,
                "village_stars_max": 6,
                "desired_skills_max": 6,
                "charm_points": {
                    "skill1_min": 1,
                    "skill1_max": 10,
                    "skill2_min": -10,
                    "skill2_max": 13,
                },
            }
        ),
    )
    packed_db.create_skill_tree(
        id=10,
        game_id=2,
        name_en="Attack",
        name_ja="Attack",
        category_tag="Offensive",
    )
    packed_db.create_skill(
        id=10,
        tree_id=10,
        name_en="Attack Up (S)",
        points=10,
    )
    for slot in range(5):
        packed_db.create_armor_piece(
            id=200 + slot,
            game_id=2,
            slot=slot,
            name_en=f"P3 Slot {slot}",
            rarity=1,
            slots=0,
            gender=2,
            hunter_type=2,
            defense=1,
            max_defense=1,
            res_fire=0,
            res_water=0,
            res_ice=0,
            res_thunder=0,
            res_dragon=0,
        )
        packed_db.set_armor_skill(armor_id=200 + slot, tree_id=10, points=3)
    kind = packed_db.create_charm_type(game_id=2, code="mystery", max_slots=3)
    packed_db.set_charm_skill_range(
        charm_type_id=kind["id"],
        tree_id=10,
        skill_slot=1,
        min_points=0,
        max_points=4,
    )
    packed_db.set_charm_slot_threshold(
        charm_type_id=kind["id"],
        fulfillment=0,
        slots=0,
    )
    packed_db.set_charm_slot_threshold(
        charm_type_id=kind["id"],
        fulfillment=1,
        slots=1,
    )
    packed_db.set_charm_slot_threshold(
        charm_type_id=kind["id"],
        fulfillment=10,
        slots=0,
    )

    client = TestClient(create_app())

    home = client.get("/")
    assert home.status_code == 200
    assert 'name="charm_mode"' in home.text
    assert 'value="one_skill"' in home.text
    assert "Use legal generated charms" not in home.text
    assert "Use my charms" not in home.text

    assert client.get("/games/mhfu/charms").status_code == 404
    bare = client.get("/games/mhp3/charms", follow_redirects=False)
    assert bare.status_code == 303

    home = client.get("/")
    assert home.status_code == 200
    assert "My talismans" in home.text
    assert "My charms" in home.text
    assert "Use legal generated charms" not in home.text
    assert 'id="talismans-modal"' in home.text
    assert 'name="skill1_points"' not in home.text
    assert home.text.count('name="skill_id"') == 6

    inventory = client.get("/games/mhp3/charms", headers={"HX-Request": "true"})
    assert inventory.status_code == 200
    assert "Add a charm" in inventory.text
    assert 'name="skill1_points"' in inventory.text
    assert "data-ss-pts-step" in inventory.text
    assert "<select" in inventory.text
    assert 'name="skill1_points"' in inventory.text
    assert 'id="skill1-points"' not in inventory.text

    added = client.post(
        "/games/mhp3/charms",
        data={"slots": "1", "skill1_tree": "10", "skill1_points": "4", "skill2_tree": ""},
    )
    assert added.status_code == 200
    assert "Attack +4" in added.text
    assert 'data-ss-pts-max="10"' in added.text
    assert 'data-ss-pts-min="-10"' in added.text
    assert 'data-ss-pts-max="13"' in added.text

    skill1_at_union = client.post(
        "/games/mhp3/charms",
        data={"slots": "1", "skill1_tree": "10", "skill1_points": "10", "skill2_tree": ""},
    )
    assert skill1_at_union.status_code == 200
    shared_range = client.post(
        "/games/mhp3/charms",
        data={"slots": "1", "skill1_tree": "10", "skill1_points": "13", "skill2_tree": ""},
    )
    assert shared_range.status_code == 422
    packed_db.create_skill_tree(
        id=11,
        game_id=2,
        name_en="Fire Res",
        name_ja="Fire Res",
        category_tag="Resistance",
    )
    s2_legal = client.post(
        "/games/mhp3/charms",
        data={
            "slots": "0",
            "skill1_tree": "10",
            "skill1_points": "4",
            "skill2_tree": "11",
            "skill2_points": "13",
        },
    )
    assert s2_legal.status_code == 200
    assert "Fire Res +13" in s2_legal.text
    s2_floor = client.post(
        "/games/mhp3/charms",
        data={
            "slots": "0",
            "skill1_tree": "10",
            "skill1_points": "1",
            "skill2_tree": "11",
            "skill2_points": "-10",
        },
    )
    assert s2_floor.status_code == 200
    s2_too_low = client.post(
        "/games/mhp3/charms",
        data={
            "slots": "0",
            "skill1_tree": "10",
            "skill1_points": "1",
            "skill2_tree": "11",
            "skill2_points": "-11",
        },
    )
    assert s2_too_low.status_code == 422

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

    extra_ids = []
    for n in range(5):
        tree_id = 20 + n
        skill_id = 20 + n
        packed_db.create_skill_tree(
            id=tree_id,
            game_id=2,
            name_en=f"Tree{n}",
            name_ja=f"Tree{n}",
        )
        packed_db.create_skill(
            id=skill_id,
            tree_id=tree_id,
            name_en=f"Skill {n}",
            points=10,
        )
        extra_ids.append(str(skill_id))
    six = client.post(
        "/games/mhp3/search",
        data={**SEARCH_FORM, "skill_id": ["10", *extra_ids]},
    )
    assert six.status_code == 200
