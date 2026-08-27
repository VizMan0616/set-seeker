#!/usr/bin/env python3
"""Build tests/fixtures/mhfu_set_mix.json from `mhfu set mix.txt`.

Athena already ships a P2G overlay: sources/MHFU-ASS/Run/Data/Languages/TeamHGG MHP2ndG/.
Official English is Languages/English MHFU/ — that is what ETL stores as name_en.
CSV strings are TeamHGG-style. Extra typos live in packs/mhfu/name_aliases.yaml.

Run from repo root: python tests/fixtures/build_mhfu_set_mix.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.etl.column_maps import mhfu as cmap
from app.etl.loaders import (
    _strip_dummy_mark,
    load_armor_file,
    load_decorations,
    load_pack,
    load_skill_blocks,
)
from app.etl.manifest import load_manifest

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "sources" / "MHFU-ASS" / "Run" / "Data"
LANG = DATA / "Languages"
MIX = REPO / "mhfu set mix.txt"
OUT = Path(__file__).resolve().parent / "mhfu_set_mix.json"
ALIASES_PATH = REPO / "packs" / "mhfu" / "name_aliases.yaml"

SLOTS = ("head", "body", "arms", "waist", "legs")
WORD_NUM = {"one": 1, "two": 2, "three": 3}

WEAPON_RE = re.compile(
    r"^(?:(\d+)|(one|two|three))[-\s]+slot\s+weapons?$", re.I
)
GEM_RE = re.compile(
    r"\[Gem\s*:?\s*\d+\s*:?\s*([^\]]+?)\]", re.I
)
GEM_LOOSE_RE = re.compile(
    r"\[Gem\s*:?\s*\d+\s*:?\s*(.+)$", re.I
)
HR_RE = re.compile(r"\bHR\s*(\d+)\b", re.I)
BBCODE_RE = re.compile(r"\[/?[bi]\]", re.I)
SEP_RE = re.compile(r"^_+$")
POST_RE = re.compile(r"^(?:post|posted)\s+by\b", re.I)
NO_GEM_RE = re.compile(r"^\[no gems?\]?$", re.I)
PROSE_RE = re.compile(
    r"^(note:|i |this |alternatively|quite simply|after gemming|"
    r"it can |works |looks |has about|i made|i do |i use |the auto)",
    re.I,
)


def _read_lang(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-16")
    names = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        names.append(s)
    return names


def _skill_sections(path: Path) -> tuple[list[str], list[str]]:
    trees, resulting = [], []
    in_res = False
    for line in path.read_text(encoding="utf-16").splitlines():
        s = line.strip()
        if s.startswith(";Resulting"):
            in_res = True
            continue
        if not s or s.startswith(";"):
            continue
        (resulting if in_res else trees).append(s)
    return trees, resulting


def norm(s: str) -> str:
    s = s.strip().lower()
    s = s.replace("’", "'")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*([+/])\s*", r"\1", s)
    compact = re.sub(r"[^a-z0-9+]+", "", s)
    return compact


class NameMaps:
    def __init__(self) -> None:
        extra = yaml.safe_load(ALIASES_PATH.read_text()) or {}
        self.armor: dict[str, str] = {}
        self.armor_by_slot: dict[int, dict[str, str]] = {i: {} for i in range(5)}
        self.csv_by_slot: dict[int, set[str]] = {i: set() for i in range(5)}
        self.deco: dict[str, str] = {}
        self.deco_csv: set[str] = set()
        self.skill: dict[str, str] = {}
        self.tree: dict[str, str] = {}
        self.skill_meta: dict[str, dict] = {}
        self.unmapped_armor: set[str] = set()
        self.unmapped_deco: set[str] = set()
        self.unmapped_skill: set[str] = set()

        pack = load_pack(load_manifest(REPO / "packs" / "mhfu"))

        for i, slot in enumerate(SLOTS):
            official = [r.name_en for r in pack.armor if r.slot == i]
            self.csv_by_slot[i] = set(official)
            for n in official:
                self._index_armor(n, n, i)
            csv_rows, _ = load_armor_file(DATA / f"{slot}.csv", i, cmap, header_lines=2)
            for csv_row, off in zip(csv_rows, official, strict=True):
                if csv_row.name_en != off:
                    self._index_armor(csv_row.name_en, off, i)
            for pack_name in ("TeamHGG MHP2ndG", "English MHFU"):
                overlay = _read_lang(LANG / pack_name / f"{slot}.txt")
                for ov, off in zip(overlay, official, strict=True):
                    cleaned, _ = _strip_dummy_mark(ov, "(dummy)")
                    if ov != off:
                        self._index_armor(ov, off, i)
                    if cleaned != off:
                        self._index_armor(cleaned, off, i)

        official_decos = [d.name_en for d in pack.decorations]
        self.deco_csv = set(official_decos)
        for n in official_decos:
            self.deco[norm(n)] = n
        csv_decos = load_decorations(DATA / "decorations.csv", cmap)
        for csv_row, off in zip(csv_decos, official_decos, strict=True):
            if csv_row.name_en != off:
                self.deco[norm(csv_row.name_en)] = off
        for pack_name in ("TeamHGG MHP2ndG", "English MHFU"):
            overlay = _read_lang(LANG / pack_name / "decorations.txt")
            for ov, off in zip(overlay, official_decos, strict=True):
                if ov != off:
                    self.deco[norm(ov)] = off

        for b in pack.skill_trees:
            self.tree[norm(b.name)] = b.name
            for pts, sname in b.thresholds:
                self.skill[norm(sname)] = sname
                self.skill_meta[sname] = {
                    "tree_name": b.name,
                    "min_points": pts,
                    "skill_name_en": sname,
                }
        csv_blocks = load_skill_blocks(DATA / "skills.txt")
        for csv_b, off_b in zip(csv_blocks, pack.skill_trees, strict=True):
            if csv_b.name != off_b.name:
                self.tree[norm(csv_b.name)] = off_b.name
            for (_, csv_s), (_, off_s) in zip(csv_b.thresholds, off_b.thresholds, strict=True):
                if csv_s != off_s:
                    self.skill[norm(csv_s)] = off_s
        for pack_name in ("TeamHGG MHP2ndG", "English MHFU"):
            trees, resulting = _skill_sections(LANG / pack_name / "skills.txt")
            official_trees = [b.name for b in pack.skill_trees]
            official_skills = [n for b in pack.skill_trees for _, n in b.thresholds]
            for ov, off in zip(trees, official_trees, strict=True):
                if ov != off:
                    self.tree[norm(ov)] = off
            for ov, off in zip(resulting, official_skills, strict=True):
                if ov != off:
                    self.skill[norm(ov)] = off

        official_armor = set().union(*self.csv_by_slot.values())
        for src, dst in (extra.get("armor") or {}).items():
            canon = self.armor.get(norm(dst), dst)
            if canon not in official_armor:
                raise SystemExit(f"name_aliases.yaml armor target not in pack: {dst!r} -> {canon!r}")
            self.armor[norm(src)] = canon
        for src, dst in (extra.get("decorations") or {}).items():
            canon = self.deco.get(norm(dst), dst)
            if canon not in self.deco_csv:
                raise SystemExit(f"name_aliases.yaml deco target not in pack: {dst!r} -> {canon!r}")
            self.deco[norm(src)] = canon
        for src, dst in (extra.get("skills") or {}).items():
            self.skill[norm(src)] = self.skill.get(norm(dst), dst)

        # Common English monster-name drift: Narga <-> Naruga
        extras = {}
        for key, val in list(self.armor.items()):
            if "naruga" in key:
                extras[key.replace("naruga", "narga")] = val
            if "narga" in key and "naruga" not in key:
                extras[key.replace("narga", "naruga")] = val
        self.armor.update(extras)

    def _index_armor(self, source: str, canonical: str, slot: int) -> None:
        k = norm(source)
        self.armor[k] = canonical
        self.armor_by_slot[slot][k] = canonical

    def map_armor(self, source: str, slot: int | None = None) -> str | None:
        source = re.sub(r"\s*\((?:gunner|blademaster|blade)\)\s*$", "", source, flags=re.I)
        k = norm(source)
        if slot is not None:
            hit = self.armor.get(k) or self.armor_by_slot[slot].get(k)
            if hit not in self.csv_by_slot[slot]:
                hit = self.armor_by_slot[slot].get(k)
            if hit not in self.csv_by_slot[slot]:
                return None
            return hit
        hit = self.armor.get(k)
        if hit is None:
            return None
        if not any(hit in names for names in self.csv_by_slot.values()):
            return None
        return hit

    def map_deco(self, source: str) -> str | None:
        hit = self.deco.get(norm(source))
        if hit not in self.deco_csv:
            return None
        return hit

    def map_skill(self, source: str) -> str | None:
        source = source.strip().rstrip("*").strip()
        return self.skill.get(norm(source))


def _clean_piece_name(raw: str) -> str:
    s = BBCODE_RE.sub("", raw).strip()
    s = re.sub(r"/b\]$", "", s).strip()
    s = s.rstrip("]").strip()
    return s


def _parse_gems(line: str) -> list[str]:
    found = [m.strip() for m in GEM_RE.findall(line)]
    if found:
        return [g for g in found if g.lower() not in ("empty slot", "no gems", "none")]
    loose = GEM_LOOSE_RE.match(line.strip())
    if loose:
        name = loose.group(1).strip().rstrip("]").strip()
        if name.lower() not in ("empty slot", "no gems", "none"):
            return [name]
    return []


def _split_gender_dual(name: str) -> list[str]:
    if "/" not in name:
        return [name]
    # Obituary/Butterfly Anca → Obituary Anca, Butterfly Anca
    left, right = name.split("/", 1)
    left, right = left.strip(), right.strip()
    lparts, rparts = left.split(), right.split()
    if len(rparts) > len(lparts):
        suffix = " ".join(rparts[1:])
        return [f"{lparts[0]} {suffix}".strip(), right]
    if len(lparts) > 1:
        suffix = " ".join(lparts[1:])
        return [left, f"{rparts[0]} {suffix}".strip()]
    return [left, right]


def parse_mix(text: str) -> list[dict]:
    hunter = "unknown"
    blocks: list[tuple[str, str, list[str]]] = []
    current: list[str] = []
    start_line = 1
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped in ("Blademaster Sets", "Gunner Sets"):
            if current:
                blocks.append((hunter, start_line, current))
                current = []
            hunter = "blademaster" if stripped.startswith("Blade") else "gunner"
            start_line = i + 1
            continue
        if SEP_RE.match(stripped):
            if current:
                blocks.append((hunter, start_line, current))
                current = []
            start_line = i + 1
            continue
        if not current and not stripped:
            start_line = i + 1
            continue
        current.append(line)
    if current:
        blocks.append((hunter, start_line, current))
    return [_parse_block(h, sl, body, lines) for h, sl, body in blocks if any(x.strip() for x in body)]


def _parse_block(hunter: str, start_line: int, body: list[str], all_lines: list[str]) -> dict:
    raw_excerpt = "\n".join(body).strip()
    cleaned = []
    for line in body:
        s = line.strip()
        if not s:
            continue
        cleaned.append(s)

    title = cleaned[0] if cleaned else f"untitled@{start_line}"
    hr = None
    m = HR_RE.search(title)
    if m:
        hr = int(m.group(1))
    author = None
    idx = 1
    if idx < len(cleaned) and POST_RE.match(cleaned[idx]):
        author = POST_RE.sub("", cleaned[idx]).strip()
        idx += 1
    elif POST_RE.match(title):
        author = POST_RE.sub("", title).strip()
        title = f"untitled@{start_line}"
        idx = 1

    weapon_slots: int | None = None
    weapon_jewels: list[str] = []
    pieces: list[tuple[str, list[str]]] = []  # name, gems
    pending_gems: list[str] = []
    target = "weapon"  # gems before first piece attach to weapon
    skills: list[str] = []
    notes: list[str] = []

    def flush_gems() -> None:
        nonlocal pending_gems, target
        if not pending_gems:
            return
        if target == "weapon":
            weapon_jewels.extend(pending_gems)
        elif pieces:
            pieces[-1][1].extend(pending_gems)
        pending_gems = []

    for line in cleaned[idx:]:
        if NO_GEM_RE.match(line) or line.lower().startswith("[no gem"):
            continue
        gems = _parse_gems(line)
        remainder = GEM_RE.sub("", line).strip()
        if gems and not GEM_RE.search(line):
            remainder = ""
        remainder = BBCODE_RE.sub("", remainder).strip()
        if gems:
            pending_gems.extend(gems)
            if not remainder:
                continue
        low = remainder.lower()
        wmatch = WEAPON_RE.match(low)
        if wmatch:
            flush_gems()
            if wmatch.group(1):
                weapon_slots = int(wmatch.group(1))
            else:
                weapon_slots = WORD_NUM[wmatch.group(2)]
            target = "weapon"
            continue
        if not remainder:
            continue
        if remainder.startswith("*") or PROSE_RE.match(remainder) or len(remainder) > 90:
            notes.append(remainder)
            continue
        if POST_RE.match(remainder):
            author = POST_RE.sub("", remainder).strip() or author
            continue
        if len(pieces) < 5:
            flush_gems()
            pieces.append((_clean_piece_name(remainder), []))
            target = "piece"
            if pending_gems:
                pieces[-1][1].extend(pending_gems)
                pending_gems = []
            continue
        if remainder.startswith("*") or PROSE_RE.match(remainder) or len(remainder) > 70:
            notes.append(remainder)
        else:
            flush_gems()
            skills.append(remainder.rstrip("*").strip())
    flush_gems()

    if weapon_slots is None:
        if weapon_jewels:
            weapon_slots = min(3, max(1, len(weapon_jewels)))
        else:
            weapon_slots = 0

    return {
        "source_line": start_line,
        "title": re.sub(r"\s*-\s*HR.*$", "", title).strip(),
        "hr": hr,
        "author": author,
        "hunter_type": hunter,
        "weapon_slots": weapon_slots,
        "weapon_jewels_src": weapon_jewels,
        "pieces_src": pieces,
        "skills_src": skills,
        "notes": notes,
        "raw": raw_excerpt[:800],
    }


def _jewel_entries(names: list[str], maps: NameMaps) -> list[dict]:
    counts: dict[str, int] = defaultdict(int)
    order: list[str] = []
    for n in names:
        key = n.strip()
        if key not in counts:
            order.append(key)
        counts[key] += 1
    out = []
    for src in order:
        name_en = maps.map_deco(src)
        if name_en is None:
            maps.unmapped_deco.add(src)
        out.append({
            "source_name": src,
            "name_en": name_en,
            "count": counts[src],
            "mapped": name_en is not None,
        })
    return out


def _piece_entry(source: str, slot: int, maps: NameMaps) -> dict:
    variants = _split_gender_dual(source)
    mapped_names = []
    for v in variants:
        name_en = maps.map_armor(v, slot)
        mapped_names.append((v, name_en))
    # Prefer a mapped variant; if both map, keep first as name_en and list alts
    primary = next((n for _, n in mapped_names if n), None)
    if primary is None:
        maps.unmapped_armor.add(source)
    alts = [n for _, n in mapped_names if n and n != primary]
    return {
        "source_name": source,
        "name_en": primary,
        "mapped": primary is not None,
        "alternates_name_en": alts,
    }


def _skill_entries(names: list[str], maps: NameMaps) -> list[dict]:
    out = []
    seen = set()
    for src in names:
        if src in seen:
            continue
        seen.add(src)
        name_en = maps.map_skill(src)
        if name_en is None:
            maps.unmapped_skill.add(src)
            out.append({
                "source_name": src,
                "skill_name_en": None,
                "tree_name": None,
                "min_points": None,
                "mapped": False,
            })
            continue
        meta = maps.skill_meta.get(name_en, {})
        out.append({
            "source_name": src,
            "skill_name_en": name_en,
            "tree_name": meta.get("tree_name"),
            "min_points": meta.get("min_points"),
            "mapped": True,
        })
    return out


def _pass_a_against_pack(record: dict, pack) -> str | None:
    """Socket + skill-point check using ETL rows (same rules as the pytest Pass A)."""
    armor_by = {}
    for row in pack.armor:
        armor_by.setdefault((row.slot, row.name_en), row)
    deco_by = {d.name_en: d for d in pack.decorations}
    pieces = []
    for slot, key in enumerate(SLOTS):
        entry = record["pieces"][key]
        if not entry.get("mapped") or not entry.get("name_en"):
            return None  # name-mapping skip already recorded
        row = armor_by.get((slot, entry["name_en"]))
        if row is None:
            return f"pack_missing:{key}:{entry['name_en']}"
        pieces.append(row)
    torso = pieces[1].torso_inc  # body
    points: dict[str, int] = {}

    def add(tree: str, pts: int, *, doubled: bool) -> None:
        points[tree] = points.get(tree, 0) + pts * (2 if doubled else 1)

    for piece in pieces:
        for tree, pts in piece.skills:
            add(tree, pts, doubled=torso and piece.slot == 1)

    def place(jewel_entries: list[dict], capacity: int, *, body: bool) -> str | None:
        used = 0
        for j in jewel_entries:
            if not j["mapped"]:
                return None
            deco = deco_by.get(j["name_en"])
            if deco is None:
                return f"pack_missing_jewel:{j['name_en']}"
            used += deco.size * j["count"]
            for tree, pts in deco.skills:
                add(tree, pts * j["count"], doubled=torso and body)
        if used > capacity:
            return f"dump_illegal_sockets:need {used} have {capacity}"
        return None

    for slot, key in enumerate(SLOTS):
        err = place(record["pieces"][key]["jewels"], pieces[slot].slots,
                    body=slot == 1)
        if err:
            return err
    err = place(record["weapon_jewels"], record["weapon_slots"] or 0, body=False)
    if err:
        return err
    missing = []
    for skill in record["skills"]:
        if not skill["mapped"] or skill["min_points"] is None or skill["min_points"] <= 0:
            continue
        got = points.get(skill["tree_name"], 0)
        if got < skill["min_points"]:
            missing.append(
                f"{skill['skill_name_en']} {skill['tree_name']} {got}<{skill['min_points']}"
            )
    if missing:
        return "dump_illegal_points:" + "; ".join(missing)
    return None


def build() -> dict:
    maps = NameMaps()
    text = MIX.read_text(encoding="utf-8", errors="replace")
    parsed = parse_mix(text)
    records = []
    for i, p in enumerate(parsed, 1):
        pieces_out = {}
        src_pieces = p["pieces_src"]
        for slot, (pname, gems) in enumerate(src_pieces[:5]):
            entry = _piece_entry(pname, slot, maps)
            entry["jewels"] = _jewel_entries(gems, maps)
            pieces_out[SLOTS[slot]] = entry
        # pad missing slots
        for slot, key in enumerate(SLOTS):
            if key not in pieces_out:
                pieces_out[key] = {
                    "source_name": None,
                    "name_en": None,
                    "mapped": False,
                    "alternates_name_en": [],
                    "jewels": [],
                    "missing": True,
                }
        weapon_jewels = _jewel_entries(p["weapon_jewels_src"], maps)
        skills = _skill_entries(p["skills_src"], maps)
        piece_mapped = all(
            pieces_out[s].get("mapped") and not pieces_out[s].get("missing")
            for s in SLOTS
        )
        jewel_lists = [weapon_jewels] + [pieces_out[s]["jewels"] for s in SLOTS]
        jewels_mapped = all(j["mapped"] for lst in jewel_lists for j in lst)
        skills_mapped = bool(skills) and all(s["mapped"] for s in skills)
        fully = piece_mapped and jewels_mapped and skills_mapped and p["weapon_slots"] is not None
        skip_reasons = []
        if not piece_mapped:
            skip_reasons.append("unmapped_piece")
        if not jewels_mapped:
            skip_reasons.append("unmapped_jewel")
        if not skills:
            skip_reasons.append("no_skills")
        elif not skills_mapped:
            skip_reasons.append("unmapped_skill")
        if p["weapon_slots"] is None:
            skip_reasons.append("unknown_weapon_slots")
        if len(src_pieces) != 5:
            skip_reasons.append(f"piece_count_{len(src_pieces)}")

        rec_id = f"{p['hunter_type']}-{i:03d}-{re.sub(r'[^a-z0-9]+', '-', p['title'].lower()).strip('-')[:48]}"
        rec = {
            "id": rec_id,
            "source_line": p["source_line"],
            "title": p["title"],
            "author": p["author"],
            "hr": p["hr"],
            "hunter_type": p["hunter_type"],
            "gender": "unknown",
            "weapon_slots": p["weapon_slots"],
            "pieces": pieces_out,
            "weapon_jewels": weapon_jewels,
            "jewels": _jewel_entries(
                p["weapon_jewels_src"]
                + [g for _, gems in src_pieces for g in gems],
                maps,
            ),
            "skills": skills,
            "fully_mapped": fully,
            "skip_reasons": skip_reasons,
            "raw": p["raw"],
        }
        records.append(rec)

    pack = load_pack(load_manifest(REPO / "packs" / "mhfu"))
    dump_illegal = []
    for rec in records:
        if not rec["fully_mapped"]:
            continue
        reason = _pass_a_against_pack(rec, pack)
        if reason:
            rec["fully_mapped"] = False
            rec["skip_reasons"] = list(rec["skip_reasons"]) + [reason]
            dump_illegal.append({"id": rec["id"], "title": rec["title"], "reason": reason})

    summary = {
        "source_file": "mhfu set mix.txt",
        "athena_commit": "134acee87dd0105f3b03dcebe78c5ea9227dafb5",
        "mapping": {
            "strategy": (
                "Official English MHFU overlay is canonical (ETL name_en). "
                "CSV/TeamHGG strings alias onto that overlay, plus "
                "packs/mhfu/name_aliases.yaml for typos/forum names. "
                "Narga/Naruga is applied as a mechanical extra. "
                "name_en must exist in the loaded pack. fully_mapped also "
                "requires Pass A (sockets + positive skill points)."
            ),
            "unmapped_armor": sorted(maps.unmapped_armor),
            "unmapped_decorations": sorted(maps.unmapped_deco),
            "unmapped_skills": sorted(maps.unmapped_skill),
            "dump_illegal": dump_illegal,
        },
        "counts": {
            "raw": len(records),
            "fully_mapped": sum(1 for r in records if r["fully_mapped"]),
            "skipped": sum(1 for r in records if not r["fully_mapped"]),
            "dump_illegal": len(dump_illegal),
        },
    }
    return {"meta": summary, "records": records}


def main() -> int:
    if not DATA.is_dir():
        print("missing sources/MHFU-ASS/Run/Data — restore per SOURCES.md", file=sys.stderr)
        return 1
    doc = build()
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    m = doc["meta"]
    print(json.dumps(m["counts"], indent=2))
    print("unmapped armor:", m["mapping"]["unmapped_armor"])
    print("unmapped deco:", m["mapping"]["unmapped_decorations"])
    print("unmapped skills:", m["mapping"]["unmapped_skills"])
    print("dump_illegal:")
    for row in m["mapping"]["dump_illegal"]:
        print(f"  {row['id']}: {row['reason']}")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
