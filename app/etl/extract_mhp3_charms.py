"""One-time extraction of MHP3 charm RNG tables from CharmDatabase.cpp.

Writes gen4-shaped CSVs under packs/mhp3/charm_generation/ (data-pack-spec.md).
Does not modify sources/. Re-run only if the pinned ASS commit changes.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CPP = REPO_ROOT / "sources" / "MHP3-ASS" / "CharmDatabase.cpp"
SKILLS = REPO_ROOT / "sources" / "MHP3-ASS" / "Run" / "Data" / "skills.txt"
OUT = REPO_ROOT / "packs" / "mhp3" / "charm_generation"

# OmaSkill::SKILL indices (`CharmDatabase.cpp:176-180`) and Omaget mapping
# (`CharmDatabase.cpp:538-550`): omakbn 0=timeworn, 1=shining, 2=mystery.
# FURU1/HIKA1/NAZO1 = in-game skill 1 (modest maxima). FURU2/HIKA2 = skill 2
# (can reach ±10, elemental res +12/+13). Do not swap these slots.
TYPES = (
    ("timeworn", 0, 1),  # FURU1, FURU2
    ("shining", 2, 3),  # HIKA1, HIKA2
    ("mystery", 4, None),  # NAZO1 only
)

_INT_TRIPLE = re.compile(r"\{\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\}")
_TABLEINIT = re.compile(r"const int tableinit\[\s*12\s*\]\s*=\s*\{([^}]+)\}")


def _ability_order_to_tree() -> dict[int, str]:
    """Ability::order → English tree name (`Skill.cpp:121-141`)."""
    mapping: dict[int, str] = {}
    with SKILLS.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if not row or not row[0].strip() or row[0].lstrip("\ufeff").startswith("#"):
                continue
            tree = row[2].strip() if len(row) > 2 else ""
            order_raw = row[7].strip() if len(row) > 7 else ""
            if not tree or not order_raw.isdigit():
                continue
            mapping[int(order_raw)] = tree
    if 0 not in mapping:
        mapping[0] = "Torso Inc"
    return mapping


def _balanced_block(text: str, start_pat: str) -> str:
    start = text.index(start_pat)
    brace = text.index("{", start)
    depth = 0
    for i, ch in enumerate(text[brace:], start=brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace : i + 1]
    raise RuntimeError(f"unclosed array after {start_pat!r}")


def _split_top_groups(block: str) -> list[str]:
    """Split `{ group, group, ... }` into the inner `{...}` groups."""
    inner = block[1:-1]
    groups: list[str] = []
    depth = 0
    begin = None
    for idx, ch in enumerate(inner):
        if ch == "{":
            if depth == 0:
                begin = idx
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and begin is not None:
                groups.append(inner[begin : idx + 1])
    return groups


def _extract_skill_tables(text: str) -> list[list[tuple[int, int, int]]]:
    block = _balanced_block(text, "static array< array< array< int >^ >^ >^ SKILL =")
    tables: list[list[tuple[int, int, int]]] = []
    for group in _split_top_groups(block):
        triples = [(int(a), int(b), int(c)) for a, b, c in _INT_TRIPLE.findall(group)]
        tables.append(triples)
    if len(tables) != 5:
        raise RuntimeError(f"expected 5 SKILL tables, got {len(tables)}")
    return tables


def _extract_furuslo(text: str) -> list[list[list[int]]]:
    block = _balanced_block(text, "static array< array< array< int >^ >^ >^ FURUSLO =")
    row_re = re.compile(r"\{([0-9, \t]+)\}")
    types: list[list[list[int]]] = []
    for chunk in _split_top_groups(block):
        rows = []
        for match in row_re.finditer(chunk):
            nums = [int(x) for x in match.group(1).split(",") if x.strip()]
            rows.append(nums)
        types.append(rows)
    if len(types) != 3:
        raise RuntimeError(f"expected 3 FURUSLO types, got {len(types)}")
    return types


def _table_seeds(text: str) -> list[int]:
    match = _TABLEINIT.search(text)
    if not match:
        raise RuntimeError("tableinit[12] not found")
    return [int(x.strip()) for x in match.group(1).split(",") if x.strip()]


def extract(out_dir: Path = OUT) -> None:
    raw = CPP.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    order_map = _ability_order_to_tree()
    skill_tables = _extract_skill_tables(text)
    furuslo = _extract_furuslo(text)
    seeds = _table_seeds(text)

    out_dir.mkdir(parents=True, exist_ok=True)

    def write_skill_csv(path: Path, triples: list[tuple[int, int, int]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["skill_tree", "min_points", "max_points"])
            for order, mn, mx in triples:
                tree = order_map.get(order)
                if tree is None:
                    raise RuntimeError(f"charm table references unknown ability order {order}")
                writer.writerow([tree, mn, mx])

    def write_slots_csv(path: Path, rows: list[list[int]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["fulfillment_value", "slot1_threshold", "slot2_threshold", "slot3_threshold"]
            )
            for fulfillment, thresholds in enumerate(rows):
                # getSlot: nn <= tbl[i] → i slots. Pad missing 1/2/3-slot cuts
                # with 99 (never reached) so every row has three columns.
                padded = list(thresholds) + [99] * 4
                writer.writerow([fulfillment, padded[1], padded[2], padded[3]])

    for code, skill1_idx, skill2_idx in TYPES:
        write_skill_csv(out_dir / f"{code}_skill1.csv", skill_tables[skill1_idx])
        if skill2_idx is not None:
            write_skill_csv(out_dir / f"{code}_skill2.csv", skill_tables[skill2_idx])
        omakbn = {"timeworn": 0, "shining": 1, "mystery": 2}[code]
        write_slots_csv(out_dir / f"{code}_slots.csv", furuslo[omakbn])

    with (out_dir / "table_seeds.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["table_index", "seed"])
        for i, seed in enumerate(seeds, start=1):
            writer.writerow([i, seed])


if __name__ == "__main__":
    extract()
    print(f"wrote charm tables under {OUT}")
