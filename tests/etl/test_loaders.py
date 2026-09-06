"""Parsing tests against vendored pack data (packs/mhfu/vendor/)."""

import pytest

from app.etl import column_maps
from app.etl.column_maps import mhfu as cmap
from app.etl.loaders import load_armor_file, load_decorations, load_skill_blocks

EXPECTED_ARMOR_COUNTS = {"head": 425, "body": 419, "arms": 410, "waist": 408, "legs": 418}


# --- column map unit tests ---


@pytest.mark.parametrize(
    "notation,expected",
    [
        ("---", 0),
        ("O--", 1),
        ("OO-", 2),
        ("OOO", 3),
    ],
)
def test_parse_slots(notation, expected):
    assert cmap.parse_slots(notation) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('"1"', 1),
        ('"6!"', 6),
        ('"5!8"', 8),
        ('"10"', 10),
    ],
)
def test_parse_level_requirement(raw, expected):
    assert cmap.parse_level_requirement(raw) == expected


def test_gender_and_hunter_type_normalization():
    # Spacing differs between files ("Male/ Female" vs "Male/Female").
    assert cmap.parse_gender("Male") == 0
    assert cmap.parse_gender("Female") == 1
    assert cmap.parse_gender("Male/ Female") == 2
    assert cmap.parse_gender("Male/Female") == 2
    assert cmap.parse_hunter_type("Blade") == 0
    assert cmap.parse_hunter_type("Gunner") == 1
    assert cmap.parse_hunter_type("Blade/ Gunner") == 2
    assert cmap.parse_hunter_type("Blade/Gunner") == 2


def test_column_map_is_pack_scoped():
    # The map must come from the mhfu module, never a shared constant.
    assert column_maps.mhfu.ARMOR["slots"] == 21
    assert column_maps.mhfu.DECORATION["skill1_points"] == 5


# --- skills.txt block format ---


def test_skill_blocks_counts(manifest):
    data_dir = manifest.source_data_path
    blocks = load_skill_blocks(data_dir / "skills.txt")
    assert len(blocks) == 99
    thresholds = [t for b in blocks for t in b.thresholds]
    assert len(thresholds) == 216
    assert sum(1 for points, _ in thresholds if points < 0) == 68


def test_skill_block_attack_exact(manifest):
    data_dir = manifest.source_data_path
    blocks = {b.name: b for b in load_skill_blocks(data_dir / "skills.txt")}
    attack = blocks["Attack"]
    assert attack.tag == "Offensive"
    assert attack.tags == ("Offensive",)
    assert attack.thresholds == (
        (20, "Attack Up (Large)"),
        (15, "Attack Up (Medium)"),
        (10, "Attack Up (Small)"),
        (-10, "Attack Dwn (Small)"),
        (-15, "Attack Dwn (Medium)"),
        (-20, "Attack Dwn (Large)"),
    )


def test_skill_block_keeps_every_athena_tag(manifest):
    data_dir = manifest.source_data_path
    blocks = {b.name: b for b in load_skill_blocks(data_dir / "skills.txt")}
    artisan = blocks["Artisan"]
    assert artisan.tags == ("Offensive", "Blademaster")
    assert artisan.tag == "Offensive"


def test_torso_inc_block_has_no_thresholds(manifest):
    data_dir = manifest.source_data_path
    blocks = {b.name: b for b in load_skill_blocks(data_dir / "skills.txt")}
    # The trailing `99` sentinel line carries no skill name and is dropped,
    # matching the legacy loader (`Skill.cpp:126-133`).
    assert blocks["Torso Inc"].thresholds == ()


# --- armor CSVs ---


@pytest.mark.parametrize("slot,stem", list(enumerate(EXPECTED_ARMOR_COUNTS)))
def test_armor_row_counts(slot, stem, manifest):
    data_dir = manifest.source_data_path
    rows, _ = load_armor_file(data_dir / f"{stem}.csv", slot, cmap, header_lines=2)
    assert len(rows) == EXPECTED_ARMOR_COUNTS[stem]
    assert all(r.slot == slot for r in rows)


def test_armor_duplicate_dropped_like_legacy(manifest):
    data_dir = manifest.source_data_path
    rows, skipped = load_armor_file(data_dir / "head.csv", 0, cmap, header_lines=2)
    assert skipped == ["Felyne Piercing"]  # legacy keeps the first occurrence
    assert sum(1 for r in rows if r.name_en == "Felyne Piercing") == 1


def test_chain_helm_exact(manifest):
    data_dir = manifest.source_data_path
    rows, _ = load_armor_file(data_dir / "head.csv", 0, cmap, header_lines=2)
    helm = next(r for r in rows if r.name_en == "Chain Helm")
    assert helm.slots == 1  # "O--"
    assert helm.rarity == 1
    assert helm.defense == 4
    assert helm.gender == 2  # "Male/ Female"
    assert helm.hunter_type == 2  # "Blade/ Gunner"
    assert helm.hr_required == 1
    assert helm.village_stars == 1
    assert (helm.res_fire, helm.res_water, helm.res_ice, helm.res_thunder, helm.res_dragon) == (
        2,
        2,
        1,
        -2,
        0,
    )
    assert helm.torso_inc is False
    assert helm.skills == (
        ("Paralysis", -1),
        ("Health", 2),
        ("Backpackng", 2),
        ("Map", 2),
        ("Whim", 2),
    )


def test_torso_inc_piece_has_flag_and_no_marker_skill(manifest):
    data_dir = manifest.source_data_path
    rows, _ = load_armor_file(data_dir / "head.csv", 0, cmap, header_lines=2)
    helm = next(r for r in rows if r.name_en == "Black Belt Helm")
    assert helm.torso_inc is True
    assert helm.skills == ()  # the Torso Inc marker row is not a skill
    assert helm.slots == 0  # "---"
    assert helm.hr_required == 8
    assert helm.village_stars == 4


def test_collapsed_level_requirement_max_wins(manifest):
    data_dir = manifest.source_data_path
    # body.csv has an Elder* value of "5!8": requires 5, available at 8.
    rows, _ = load_armor_file(data_dir / "body.csv", 1, cmap, header_lines=2)
    assert any(r.village_stars == 8 for r in rows)


# --- decorations.csv (no header) ---


def test_decoration_count_and_attack_jewel(manifest):
    data_dir = manifest.source_data_path
    rows = load_decorations(data_dir / "decorations.csv", cmap)
    assert len(rows) == 168
    jewel = next(r for r in rows if r.name_en == "Attack Jewel")
    assert jewel.size == 1  # "O--"
    assert jewel.hr_required == 1
    assert jewel.skills == (("Attack", 1),)


def test_dual_skill_decoration_keeps_negative_points(manifest):
    data_dir = manifest.source_data_path
    rows = load_decorations(data_dir / "decorations.csv", cmap)
    fierce = next(r for r in rows if r.name_en == "Fierce Jewel")
    assert fierce.size == 2  # "OO-"
    assert fierce.skills == (("Attack", 3), ("Defence", -1))


# --- whole-pack load ---


def test_dummy_flag_comes_from_english_overlay(pack_data):
    helm = next(r for r in pack_data.armor if r.name_en == "Red Lobster Helm")
    chain = next(r for r in pack_data.armor if r.name_en == "Chain Helm")
    assert helm.is_dummy is True
    assert chain.is_dummy is False


def test_load_pack_totals(pack_data):
    assert len(pack_data.skill_trees) == 99
    assert len(pack_data.armor) == 2080
    assert len(pack_data.decorations) == 168
    assert sorted(set(pack_data.duplicates_skipped)) == ["Felyne Piercing"]
    # Official English overlay, not TeamHGG CSV strings.
    trees = {b.name for b in pack_data.skill_trees}
    assert "AutoReload" in trees
    assert "Speed Fire" not in trees
    skills = {name for b in pack_data.skill_trees for _, name in b.thresholds}
    assert "Normal S All LV Add" in skills
    assert "All Shots Up" not in skills
    jewels = {d.name_en for d in pack_data.decorations}
    assert "Cont. Fire Jewel" in jewels
    assert "SpeedFire Jewel" not in jewels
    # Every referenced tree must resolve (referential integrity at parse level).
    tree_names = {b.name for b in pack_data.skill_trees}
    for row in pack_data.armor:
        for tree, _ in row.skills:
            assert tree in tree_names
    for row in pack_data.decorations:
        for tree, _ in row.skills:
            assert tree in tree_names
