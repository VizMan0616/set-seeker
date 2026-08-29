"""End-to-end writer tests: real files -> repository -> schema."""

from app.etl.writer import PackWriter, table_counts
from app.repository.user_data import UserDataRepository

EXPECTED_COUNTS = {
    "games": 1,
    "skill_trees": 99,
    "skills": 216,
    "skill_tree_tags": 101,
    "skill_categories": 8,
    "armor_pieces": 2080,
    "armor_skills": 7142,
    "decorations": 168,
    "decoration_skills": 281,
    "charm_types": 0,
    "charm_skill_ranges": 0,
    "charm_slot_thresholds": 0,
}


def test_pack_stores_progression_caps(etl_db):
    import json

    repo, game_id, _ = etl_db
    game = repo.get_game(game_id)
    features = json.loads(game["features"])
    assert features["guild_rank_max"] == 9
    assert features["village_stars_max"] == 9
    assert features["desired_skills_max"] == 5


def test_loaded_row_counts(etl_db):
    repo, game_id, counts = etl_db
    assert counts == EXPECTED_COUNTS
    assert table_counts(repo, game_id) == {
        k: v for k, v in EXPECTED_COUNTS.items() if k != "games"
    }


def test_chain_helm_spot_check_in_db(etl_db):
    repo, game_id, _ = etl_db
    helm = next(p for p in repo.list_armor_pieces(game_id, slot=0, allow_event=True)
                if p["name_en"] == "Chain Helm")
    assert helm["slots"] == 1
    assert helm["rarity"] == 1
    assert helm["defense"] == 4
    assert helm["max_defense"] == 4  # MHFU data has one defence value
    assert helm["gender"] == 2
    assert helm["hunter_type"] == 2
    assert helm["hr_required"] == 1
    assert helm["village_stars"] == 1
    assert helm["torso_inc"] in (False, 0)
    tree_names = {t["id"]: t["name_en"] for t in repo.list_skill_trees(game_id)}
    skills = {tree_names[s["tree_id"]]: s["points"]
              for s in repo.list_armor_skills_for_piece(helm["id"])}
    assert skills == {"Paralysis": -1, "Health": 2, "Backpackng": 2, "Map": 2,
                      "Whim": 2}


def test_bilingual_names_populated_via_fallback(etl_db):
    # MHFU-ASS ships no Japanese names; name_ja falls back to English
    # (data-pack-spec.md ETL rule 2).
    repo, game_id, _ = etl_db
    piece = repo.list_armor_pieces(game_id, slot=0, allow_event=True)[0]
    assert piece["name_ja"] == piece["name_en"]
    tree = repo.list_skill_trees(game_id)[0]
    assert tree["name_ja"] == tree["name_en"]
    skill = repo.list_skills_for_tree(tree["id"])[0]
    assert skill["name_ja"] == skill["name_en"]
    deco = repo.list_decorations(game_id, allow_event=True)[0]
    assert deco["name_ja"] == deco["name_en"]


def test_pack_scoped_tags_and_dummy_flag(etl_db):
    repo, game_id, _ = etl_db
    tags = [c["tag"] for c in repo.list_skill_categories(game_id)]
    assert tags == [
        "Offensive", "Defensive", "Resistance", "Blademaster",
        "Bowgun", "Bow", "Treasure Hunting", "Farming",
    ]
    artisan = next(t for t in repo.list_skill_trees(game_id) if t["name_en"] == "Artisan")
    artisan_tags = {r["tag"] for r in repo.list_skill_tree_tags(artisan["id"])}
    assert artisan_tags == {"Offensive", "Blademaster"}
    helm = next(p for p in repo.list_armor_pieces(game_id, slot=0, allow_event=True)
                if p["name_en"] == "Red Lobster Helm")
    assert helm["is_dummy"] in (True, 1)


def test_negative_skills_flagged(etl_db):
    repo, game_id, _ = etl_db
    attack = next(t for t in repo.list_skill_trees(game_id)
                  if t["name_en"] == "Attack")
    by_name = {s["name_en"]: s for s in repo.list_skills_for_tree(attack["id"])}
    assert by_name["Attack Up (Large)"]["points"] == 20
    assert by_name["Attack Up (Large)"]["is_negative"] in (False, 0)
    assert by_name["Attack Down (Large)"]["points"] == -20
    assert by_name["Attack Down (Large)"]["is_negative"] in (True, 1)


def test_rebuild_is_idempotent_and_preserves_user_data(etl_db, manifest, pack_data):
    repo, game_id, counts = etl_db
    user_repo = UserDataRepository(repo._engine)

    session = user_repo.get_or_create_session("etl-test-session")
    attack_tree = next(t for t in repo.list_skill_trees(game_id)
                       if t["name_en"] == "Attack")
    charm = user_repo.add_charm(session_id=session["id"], game_id=game_id, slots=2,
                                skill1_tree=attack_tree["id"], skill1_points=5)
    state = user_repo.create_search_state(session_id=session["id"], game_id=game_id,
                                          query_json="{}")

    second = PackWriter(repo).rebuild_pack(manifest, pack_data)
    assert second == counts
    # The games row is reused, so user-table foreign keys stay valid.
    assert repo.get_game_by_code("mhfu")["id"] == game_id
    assert table_counts(repo, game_id) == {
        k: v for k, v in EXPECTED_COUNTS.items() if k != "games"
    }

    # User data untouched (run-etl rule 2).
    assert user_repo.get_session("etl-test-session") is not None
    surviving = user_repo.get_charm(charm["id"])
    assert surviving is not None
    assert surviving["game_id"] == game_id
    # Deterministic ids: the charm's skill-tree reference still resolves.
    assert repo.get_skill_tree(surviving["skill1_tree"])["name_en"] == "Attack"
    assert user_repo.get_search_state(state["id"]) is not None


def test_deterministic_piece_ids_across_rebuilds(etl_db, manifest, pack_data):
    repo, game_id, _ = etl_db
    before = {p["name_en"]: p["id"]
              for p in repo.list_armor_pieces(game_id, slot=0, allow_event=True)}
    PackWriter(repo).rebuild_pack(manifest, pack_data)
    after = {p["name_en"]: p["id"]
             for p in repo.list_armor_pieces(game_id, slot=0, allow_event=True)}
    assert before == after
