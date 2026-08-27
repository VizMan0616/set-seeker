"""Parse legacy pack files into plain row dataclasses (no database access here).

Field positions come exclusively from the pack's column map module
(`app/etl/column_maps/<pack_id>.py`) — never from shared positional constants.
"""

import csv
import importlib
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from app.etl.manifest import PackManifest

SLOT_FILES = ("head", "body", "arms", "waist", "legs")

_THRESHOLD_LINE = re.compile(r'^(-?\d+)\s+"(.+)"$')


@dataclass(frozen=True)
class SkillTreeBlock:
    name: str
    tag: str | None
    thresholds: tuple[tuple[int, str], ...]  # (points, skill name), signed
    tags: tuple[str, ...] = ()               # all Athena tags; tag is tags[0]


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
    is_dummy: bool
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
    tags: list[str] = []
    thresholds: list[tuple[int, str]] = []

    def close() -> None:
        nonlocal name, tags, thresholds
        if name is not None:
            blocks.append(SkillTreeBlock(
                name=name,
                tag=tags[0] if tags else None,
                tags=tuple(tags),
                thresholds=tuple(thresholds),
            ))
        name, tags, thresholds = None, [], []

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            close()
            continue
        if line.startswith('"'):
            close()
            name = line.strip('"')
        elif line.lower().startswith("tag"):
            tag = line.partition("=")[2].strip().strip('"')
            if tag and tag not in tags:
                tags.append(tag)
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
                is_dummy=getattr(cmap, "DUMMY_MARK", "(dummy)").lower() in name.lower(),
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


def _read_locale_names(path: Path) -> list[str]:
    """Athena language lists are UTF-16 with a `;Slot:` header line."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines and (lines[0].startswith(";") or lines[0].endswith(":")):
        lines = lines[1:]
    return lines


def _read_skill_overlay(path: Path) -> tuple[list[str], list[str]]:
    """English skills.txt: tree names, then ``;Resulting Skills`` threshold names."""
    raw = path.read_bytes()
    text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    trees: list[str] = []
    resulting: list[str] = []
    in_resulting = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(";Resulting"):
            in_resulting = True
            continue
        if not stripped or stripped.startswith(";"):
            continue
        (resulting if in_resulting else trees).append(stripped)
    return trees, resulting


def _strip_dummy_mark(name: str, mark: str) -> tuple[str, bool]:
    """Overlay rows prefix ``(dummy)``; the flag is stored separately."""
    dummy = mark.lower() in name.lower()
    if not dummy:
        return name, False
    index = name.lower().find(mark.lower())
    cleaned = (name[:index] + name[index + len(mark) :]).strip()
    return cleaned, True


def _require_len(kind: str, got: int, expected: int) -> None:
    if got != expected:
        raise RuntimeError(
            f"English overlay {kind} has {got} names, expected {expected} "
            f"(CSV rows after duplicate collapse)"
        )


def apply_official_english_overlay(
    skill_trees: tuple[SkillTreeBlock, ...],
    armor: tuple[ArmorRow, ...],
    decorations: tuple[DecorationRow, ...],
    data_dir: Path,
    cmap,
) -> tuple[tuple[SkillTreeBlock, ...], tuple[ArmorRow, ...], tuple[DecorationRow, ...]]:
    """Replace CSV/TeamHGG name_en with Languages/English MHFU (official EN).

    Athena ``LoadLanguage`` overlays names positionally. MHFU CSV strings follow
    the TeamHGG P2G fan pack; official Freedom Unite English lives in the
    English MHFU folder (AutoReload, Normal S All LV Add, Cont. Fire Jewel, …).
    """
    locale_rel = getattr(cmap, "ENGLISH_LOCALE_DIR", None)
    if not locale_rel:
        return skill_trees, armor, decorations
    locale_dir = data_dir / locale_rel
    if not locale_dir.is_dir():
        raise RuntimeError(f"official English overlay missing: {locale_dir}")

    mark = getattr(cmap, "DUMMY_MARK", "(dummy)")
    tree_names, skill_names = _read_skill_overlay(locale_dir / "skills.txt")
    _require_len("skill trees", len(tree_names), len(skill_trees))
    n_thresholds = sum(len(block.thresholds) for block in skill_trees)
    _require_len("resulting skills", len(skill_names), n_thresholds)

    tree_map = {
        block.name: official
        for block, official in zip(skill_trees, tree_names, strict=True)
    }
    remapped_trees: list[SkillTreeBlock] = []
    cursor = 0
    for block, official_tree in zip(skill_trees, tree_names, strict=True):
        count = len(block.thresholds)
        new_thresholds = tuple(
            (points, skill_names[cursor + i])
            for i, (points, _) in enumerate(block.thresholds)
        )
        cursor += count
        remapped_trees.append(replace(block, name=official_tree, thresholds=new_thresholds))

    remapped_armor: list[ArmorRow] = []
    for slot, stem in enumerate(SLOT_FILES):
        names = _read_locale_names(locale_dir / f"{stem}.txt")
        pieces = [row for row in armor if row.slot == slot]
        _require_len(stem, len(names), len(pieces))
        for row, overlay_name in zip(pieces, names, strict=True):
            cleaned, dummy = _strip_dummy_mark(overlay_name, mark)
            remapped_armor.append(
                replace(
                    row,
                    name_en=cleaned,
                    is_dummy=dummy,
                    skills=tuple((tree_map.get(tree, tree), pts) for tree, pts in row.skills),
                )
            )

    deco_names = _read_locale_names(locale_dir / "decorations.txt")
    _require_len("decorations", len(deco_names), len(decorations))
    remapped_decos = tuple(
        replace(
            row,
            name_en=name,
            skills=tuple((tree_map.get(tree, tree), pts) for tree, pts in row.skills),
        )
        for row, name in zip(decorations, deco_names, strict=True)
    )
    return tuple(remapped_trees), tuple(remapped_armor), remapped_decos


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

    skill_trees, armor_rows, decorations = apply_official_english_overlay(
        tuple(load_skill_blocks(data_dir / "skills.txt")),
        tuple(armor),
        tuple(load_decorations(data_dir / f"decorations.{ext}", cmap)),
        data_dir,
        cmap,
    )
    return PackData(
        manifest=manifest,
        skill_trees=skill_trees,
        armor=armor_rows,
        decorations=decorations,
        duplicates_skipped=tuple(skipped),
    )
