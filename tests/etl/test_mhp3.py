"""MHP3 pack: column map, source parse, writer, and CLI gate."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.etl.column_maps import mhp3 as cmap
from app.etl.loaders import load_armor_file, load_decorations, load_pack, load_skill_table
from app.etl.manifest import load_manifest
from app.etl.writer import PackWriter, table_counts
from app.repository import tables
from app.repository.game_data import GameDataRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "packs" / "mhp3"
DATA_DIR = REPO_ROOT / "sources" / "MHP3-ASS" / "Run" / "Data"

EXPECTED_ARMOR = {"head": 226, "body": 226, "arms": 208, "waist": 207, "legs": 213}


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(PACK_DIR)


@pytest.fixture(scope="module")
def pack_data(manifest):
    return load_pack(manifest)


@pytest.fixture(scope="module")
def etl_db(tmp_path_factory, manifest, pack_data):
    db_path = tmp_path_factory.mktemp("etl") / "mhp3.db"
    engine = create_engine(f"sqlite:///{db_path}")
    tables.metadata.create_all(engine)
    repo = GameDataRepository(engine)
    counts = PackWriter(repo).rebuild_pack(manifest, pack_data)
    game_id = repo.get_game_by_code("mhp3")["id"]
    return repo, game_id, counts


def test_column_map_is_pack_scoped():
    assert cmap.ARMOR["slots"] == 5
    assert cmap.DECORATION["skill1_tree"] == 6
    assert cmap.ARMOR_DEDUP == "name"


def test_athena_012_gender_and_type():
    assert cmap.parse_gender("1") == 0
    assert cmap.parse_gender("2") == 1
    assert cmap.parse_gender("0") == 2
    assert cmap.parse_hunter_type("1") == 0
    assert cmap.parse_hunter_type("2") == 1
    assert cmap.parse_hunter_type("0") == 2
    assert cmap.parse_slots("3") == 3


def test_skill_table_counts():
    blocks = load_skill_table(DATA_DIR / "skills.txt", cmap)
    assert len(blocks) == 100
    assert sum(len(b.thresholds) for b in blocks) == 209
    torso = next(b for b in blocks if b.name == "Torso Inc")
    assert torso.thresholds == ()
    attack = next(b for b in blocks if b.name == "Attack")
    assert attack.name_ja == "攻撃"
    assert attack.thresholds[2] == (20, "Attack Up [Lg]")


@pytest.mark.parametrize("slot,stem", list(enumerate(EXPECTED_ARMOR)))
def test_armor_row_counts(slot, stem):
    rows, _ = load_armor_file(DATA_DIR / f"{stem}.txt", slot, cmap, header_lines=0)
    assert len(rows) == EXPECTED_ARMOR[stem]


def test_name_only_duplicates_dropped():
    rows, skipped = load_armor_file(DATA_DIR / "head.txt", 0, cmap, header_lines=0)
    assert "Nightmare Furore" in skipped
    assert sum(1 for r in rows if r.name_en == "Nightmare Furore") == 1


def test_chain_helm_and_torso_inc():
    rows, _ = load_armor_file(DATA_DIR / "head.txt", 0, cmap, header_lines=0)
    helm = next(r for r in rows if r.name_en == "Chain Helm")
    assert helm.name_ja == "チェーンヘッド"
    assert helm.slots == 1
    assert helm.defense == 2
    assert helm.max_defense == 22
    assert helm.gender == 2
    assert helm.skills == (("Health", 2), ("Combo Rate", 4), ("Shot Mix", 1))
    skull = next(r for r in rows if r.name_en == "Skull Face")
    assert skull.torso_inc is True
    assert skull.skills == ()


def test_decorations():
    rows = load_decorations(DATA_DIR / "decorations.txt", cmap)
    assert len(rows) == 164
    jewel = next(r for r in rows if r.name_en == "Attack Jewel[1]")
    assert jewel.size == 1
    assert jewel.rarity == 4
    assert jewel.skills == (("Attack", 1), ("Defense", -1))


def test_load_pack_charms_and_fan_names(pack_data, manifest):
    assert manifest.translation == "fan"
    assert manifest.progression == {"guild_rank": 6, "village_stars": 6}
    assert len(pack_data.armor) == 1080
    assert len(pack_data.duplicates_skipped) == 26
    assert {c.code for c in pack_data.charm_types} == {"mystery", "shining", "timeworn"}
    trees = {b.name for b in pack_data.skill_trees}
    for charm in pack_data.charm_types:
        for rng in charm.ranges:
            assert rng.tree in trees


def test_writer_counts_and_progression(etl_db):
    import json

    repo, game_id, counts = etl_db
    assert counts["armor_pieces"] == 1080
    assert counts["charm_types"] == 3
    features = json.loads(repo.get_game(game_id)["features"])
    assert features["guild_rank_max"] == 6
    assert features["village_stars_max"] == 6
    assert features["talismans"] is True
    assert features["charm_tables"] is True
    assert features["translation"] == "fan"
    helm = next(p for p in repo.list_armor_pieces(game_id, slot=0, allow_event=True)
                if p["name_en"] == "Chain Helm")
    assert helm["name_ja"] == "チェーンヘッド"
    assert helm["max_defense"] == 22
    assert table_counts(repo, game_id)["charm_skill_ranges"] == 265


def test_cli_end_to_end(tmp_path):
    import subprocess
    import sys

    db_path = tmp_path / "cli.db"
    proc = subprocess.run(
        [sys.executable, "-m", "app.etl", "--pack", "mhp3",
         "--database-url", f"sqlite:///{db_path}"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "[etl]   armor_pieces: 1080" in proc.stdout
    assert "[etl]   charm_types: 3" in proc.stdout
    assert "[gate] all checks passed" in proc.stdout
