"""MHP3 pack: column map, source parse, writer, and CLI gate."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.etl.column_maps import mhp3 as cmap
from app.etl.loaders import (
    charm_point_union,
    load_armor_file,
    load_decorations,
    load_pack,
    load_skill_table,
)
from app.etl.manifest import load_manifest
from app.etl.writer import PackWriter, table_counts
from app.repository import tables
from app.repository.game_data import GameDataRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "packs" / "mhp3"

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


def test_manifest_locale_path(manifest):
    assert manifest.english_locale_path == PACK_DIR / "vendor" / "locales" / "en"


def test_athena_012_gender_and_type():
    assert cmap.parse_gender("1") == 0
    assert cmap.parse_gender("2") == 1
    assert cmap.parse_gender("0") == 2
    assert cmap.parse_hunter_type("1") == 0
    assert cmap.parse_hunter_type("2") == 1
    assert cmap.parse_hunter_type("0") == 2
    assert cmap.parse_slots("3") == 3


def test_skill_table_counts(manifest):
    data_dir = manifest.source_data_path
    blocks = load_skill_table(data_dir / "skills.txt", cmap)
    assert len(blocks) == 100
    assert sum(len(b.thresholds) for b in blocks) == 209
    torso = next(b for b in blocks if b.name == "Torso Inc")
    assert torso.thresholds == ()
    attack = next(b for b in blocks if b.name == "Attack")
    assert attack.name_ja == "攻撃"
    assert attack.thresholds[2] == (20, "Attack Up [Lg]")


@pytest.mark.parametrize("slot,stem", list(enumerate(EXPECTED_ARMOR)))
def test_armor_row_counts(slot, stem, manifest):
    data_dir = manifest.source_data_path
    rows, _ = load_armor_file(data_dir / f"{stem}.txt", slot, cmap, header_lines=0)
    assert len(rows) == EXPECTED_ARMOR[stem]


def test_name_only_duplicates_dropped(manifest):
    data_dir = manifest.source_data_path
    rows, skipped = load_armor_file(data_dir / "head.txt", 0, cmap, header_lines=0)
    assert "Nightmare Furore" in skipped
    assert sum(1 for r in rows if r.name_en == "Nightmare Furore") == 1


def test_chain_helm_and_torso_inc(manifest):
    data_dir = manifest.source_data_path
    rows, _ = load_armor_file(data_dir / "head.txt", 0, cmap, header_lines=0)
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


def test_decorations(manifest):
    data_dir = manifest.source_data_path
    rows = load_decorations(data_dir / "decorations.txt", cmap)
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
    assert pack_data.english_overlay_unmapped == 0
    assert {c.code for c in pack_data.charm_types} == {"mystery", "shining", "timeworn"}
    trees = {b.name for b in pack_data.skill_trees}
    assert "Handicraft" in trees
    assert "Artisan" not in trees
    assert "Torso Up" in trees
    assert "Torso Inc" not in trees
    from app.etl.loaders import torso_inc_skill_name

    assert torso_inc_skill_name(pack_data) == "Torso Up"
    helm = next(r for r in pack_data.armor if r.name_en == "Chainmail Headgear")
    assert helm.name_ja == "チェーンヘッド"
    assert helm.skills == (("Health", 2), ("Combo Rate", 4), ("Combo Plus", 1))
    jewel = next(d for d in pack_data.decorations if d.name_en == "Attack Jewel 1")
    assert jewel.skills == (("Attack", 1), ("Defense", -1))
    skills = {name for b in pack_data.skill_trees for _, name in b.thresholds}
    assert "Attack Up (L)" in skills
    assert "Attack Up [Lg]" not in skills
    for charm in pack_data.charm_types:
        for rng in charm.ranges:
            assert rng.tree in trees
    assert any(rng.tree == "Hearing" for c in pack_data.charm_types for rng in c.ranges)
    assert not any(rng.tree == "HearProtct" for c in pack_data.charm_types for rng in c.ranges)


def test_charm_point_union_is_csv_envelope_not_plus_seven(pack_data):
    bounds = charm_point_union(pack_data.charm_types)
    assert bounds == {
        "skill1_min": 1,
        "skill1_max": 10,
        "skill2_min": -10,
        "skill2_max": 13,
    }
    skill1_hi = max(
        rng.max_points for c in pack_data.charm_types for rng in c.ranges if rng.skill_slot == 1
    )
    assert skill1_hi == 10


def test_writer_counts_and_progression(etl_db):
    import json

    repo, game_id, counts = etl_db
    assert counts["armor_pieces"] == 1080
    assert counts["charm_types"] == 3
    features = json.loads(repo.get_game(game_id)["features"])
    assert features["guild_rank_max"] == 6
    assert features["village_stars_max"] == 6
    assert features["desired_skills_max"] == 6
    assert features["charm_points"]["skill1_max"] == 10
    assert features["charm_points"]["skill2_max"] == 13
    assert features["charm_points"]["skill2_min"] == -10
    assert features["talismans"] is True
    assert features["charm_tables"] is True
    assert features["translation"] == "fan"
    assert features["torso_inc_name"] == "Torso Up"
    assert features["data_version"] == 1
    helm = next(
        p
        for p in repo.list_armor_pieces(game_id, slot=0, allow_event=True)
        if p["name_en"] == "Chainmail Headgear"
    )
    assert helm["name_ja"] == "チェーンヘッド"
    assert helm["max_defense"] == 22
    assert table_counts(repo, game_id)["charm_skill_ranges"] == 265


def test_pack_loader_applies_slot_thresholds_to_generated_charms(etl_db):
    from app.domain.models import Query, SkillRequest
    from app.engine.charms import charm_candidates
    from app.pack_loader import PackLoader

    repo, game_id, _ = etl_db
    pack = PackLoader(repo)("mhp3")
    assert sum(len(k.slot_thresholds) for k in pack.charm_types) == 53
    trees = {t["name_en"]: t["id"] for t in repo.list_skill_trees(game_id)}
    attack = trees["Attack"]
    query = Query(
        game="mhp3",
        skills=(SkillRequest(tree_id=attack, min_points=20),),
        weapon_slots=0,
        gender="m",
        hunter_type="blademaster",
        hr=None,
        village_stars=None,
    )
    generated = [c for c in charm_candidates(pack, query) if c.id < 0]
    attack_pts = [dict(c.skills).get(attack, 0) for c in generated if c.skills]
    assert attack_pts
    # Attack-only query: one-skill charms use skill1 (mystery/shining +4).
    assert max(attack_pts) <= 4
    # Mystery Attack +4 cannot pair with 3 slots under FURUSLO.
    assert not any(c.slots == 3 and c.skills == ((attack, 4),) for c in generated)


def test_cli_end_to_end(tmp_path):
    import subprocess
    import sys

    db_path = tmp_path / "cli.db"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.etl",
            "--pack",
            "mhp3",
            "--database-url",
            f"sqlite:///{db_path}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "[etl]   armor_pieces: 1080" in proc.stdout
    assert "[etl]   charm_types: 3" in proc.stdout
    assert "[gate] all checks passed" in proc.stdout
