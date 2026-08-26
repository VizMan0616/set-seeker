"""Parse legacy pack files into plain row dataclasses (no database access here).

Field positions come exclusively from the pack's column map module
(`app/etl/column_maps/<pack_id>.py`) — never from shared positional constants.
"""

import csv
import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.etl.manifest import PackManifest

SLOT_FILES = ("head", "body", "arms", "waist", "legs")

_THRESHOLD_LINE = re.compile(r'^(-?\d+)\s+"(.+)"$')


@dataclass(frozen=True)
class SkillTreeBlock:
    name: str
    tag: str | None
    thresholds: tuple[tuple[int, str], ...]  # (points, skill name), signed


@dataclass(frozen=True)
class ArmorRow:
    slot: int
    name_en: str
    gender: int
    hunter_type: int
    rarity: int
    slots: int
    hr_required: int
    village_stars: int
    defense: int
    res_fire: int
    res_water: int
    res_ice: int
    res_thunder: int
    res_dragon: int
    torso_inc: bool
    skills: tuple[tuple[str, int], ...]  # (tree name, points); Torso Inc excluded


@dataclass(frozen=True)
class DecorationRow:
    name_en: str
    size: int
    hr_required: int
    village_stars: int
    skills: tuple[tuple[str, int], ...]  # (tree name, points), negative allowed


@dataclass(frozen=True)
class PackData:
    manifest: PackManifest
    skill_trees: tuple[SkillTreeBlock, ...]
    armor: tuple[ArmorRow, ...]
    decorations: tuple[DecorationRow, ...]
    duplicates_skipped: tuple[str, ...] = field(default_factory=tuple)


def load_skill_blocks(path: Path) -> list[SkillTreeBlock]:
    """MHFU block format (`Skill.cpp:64+`): `"Ability"` line, optional `tag="..."`
    lines, then `points "Skill Name"` lines; blocks are blank-line separated.

    A points line without a quoted name (the `99` sentinel under "Torso Inc")
    carries no skill and is skipped, matching the legacy loader, which discards
    the partially built final block.
    """
    blocks: list[SkillTreeBlock] = []
    name: str | None = None
    tag: str | None = None
    thresholds: list[tuple[int, str]] = []

    def close() -> None:
        nonlocal name, tag, thresholds
        if name is not None:
            blocks.append(SkillTreeBlock(name=name, tag=tag,
                                         thresholds=tuple(thresholds)))
        name, tag, thresholds = None, None, []

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            close()
            continue
        if line.startswith('"'):
            close()
            name = line.strip('"')
        elif line.lower().startswith("tag"):
            if tag is None:  # schema stores one category_tag; first tag wins
                tag = line.partition("=")[2].strip().strip('"')
        else:
            match = _THRESHOLD_LINE.match(line)
            if match:
                thresholds.append((int(match.group(1)), match.group(2)))
    close()
    return blocks


def load_armor_file(path: Path, slot: int, cmap,
                    header_lines: int) -> tuple[list[ArmorRow], list[str]]:
    """One armor CSV. Returns (rows, skipped duplicate names).

    Duplicates: the legacy loader drops later rows sharing (name, gender)
    (`Armor.cpp:10-16, 48`); we keep the first occurrence to match its counts.
    """
    cols = cmap.ARMOR
    rows: list[ArmorRow] = []
    skipped: list[str] = []
    seen: set[tuple[str, int]] = set()
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for _ in range(header_lines):
            next(reader, None)
        for fields in reader:
            if not fields or not fields[cols["name"]].strip():
                continue
            gender = cmap.parse_gender(fields[cols["gender"]])
            name = fields[cols["name"]].strip()
            if (name, gender) in seen:
                skipped.append(name)
                continue
            seen.add((name, gender))

            skills: list[tuple[str, int]] = []
            torso_inc = False
            for i in range(cols["skill_pairs"]):
                tree = fields[cols["skill_start"] + i * 2].strip()
                points = fields[cols["skill_start"] + i * 2 + 1].strip()
                if not tree:
                    continue
                if tree == cmap.TORSO_INC_TREE:
                    torso_inc = True
                    continue
                if not points:
                    continue  # legacy keeps these at 0 points; they carry no information
                skills.append((tree, int(points)))

            rows.append(ArmorRow(
                slot=slot,
                name_en=name,
                gender=gender,
                hunter_type=cmap.parse_hunter_type(fields[cols["hunter_type"]]),
                rarity=int(fields[cols["rarity"]]),
                slots=cmap.parse_slots(fields[cols["slots"]]),
                hr_required=cmap.parse_level_requirement(fields[cols["hr"]]),
                village_stars=cmap.parse_level_requirement(fields[cols["village"]]),
                defense=int(fields[cols["defense"]]),
                res_fire=int(fields[cols["res_fire"]]),
                res_water=int(fields[cols["res_water"]]),
                res_ice=int(fields[cols["res_ice"]]),
                res_thunder=int(fields[cols["res_thunder"]]),
                res_dragon=int(fields[cols["res_dragon"]]),
                torso_inc=torso_inc,
                skills=tuple(skills),
            ))
    return rows, skipped


def load_decorations(path: Path, cmap) -> list[DecorationRow]:
    """Header-less decorations CSV (`Decoration.cpp:55-108`)."""
    cols = cmap.DECORATION
    rows: list[DecorationRow] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for fields in csv.reader(fh):
            if not fields or not fields[cols["name"]].strip():
                continue
            skills: list[tuple[str, int]] = []
            for points_key, tree_key in (("skill1_points", "skill1_tree"),
                                         ("skill2_points", "skill2_tree")):
                tree = fields[cols[tree_key]].strip()
                points = fields[cols[points_key]].strip()
                if tree and points:
                    skills.append((tree, int(points)))
            rows.append(DecorationRow(
                name_en=fields[cols["name"]].strip(),
                size=cmap.parse_slots(fields[cols["slots"]]),
                hr_required=cmap.parse_level_requirement(fields[cols["hr"]]),
                village_stars=cmap.parse_level_requirement(fields[cols["village"]]),
                skills=tuple(skills),
            ))
    return rows


def load_pack(manifest: PackManifest) -> PackData:
    """Load every source file for the pack, bound to its own column map."""
    cmap = importlib.import_module(f"app.etl.column_maps.{manifest.id}")
    data_dir = manifest.source_data_path
    ext = manifest.formats["armor_file_ext"]

    armor: list[ArmorRow] = []
    skipped: list[str] = []
    header_lines = int(manifest.formats["armor_header_lines"])
    for slot, stem in enumerate(SLOT_FILES):
        rows, dupes = load_armor_file(data_dir / f"{stem}.{ext}", slot, cmap,
                                      header_lines)
        armor.extend(rows)
        skipped.extend(dupes)

    return PackData(
        manifest=manifest,
        skill_trees=tuple(load_skill_blocks(data_dir / "skills.txt")),
        armor=tuple(armor),
        decorations=tuple(load_decorations(data_dir / f"decorations.{ext}", cmap)),
        duplicates_skipped=tuple(skipped),
    )
