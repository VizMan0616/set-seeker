"""MHP3 column map — positional parsing for Portable 3rd files ONLY.

Never reuse these positions for another pack (run-etl rule 1). Derived from
sources/MHP3-ASS @ a22f3ac2:

- Armor:  `Armor.cpp:18-103` (``#`` comment header, integer slots, name-only
  duplicate drop, Athena ``0/1/2`` gender and hunter type)
- Decor.: `Decoration.cpp:8-80` (comment header; tree then points)
- Skills: `Skill.cpp:64-131` (tabular, no leading index columns; empty
  ability column = Torso Inc)
"""

# --- armor TXT (head/body/arms/waist/legs.txt) ---

ARMOR = {
    "name": 0,
    "name_ja": 1,
    "gender": 2,  # 0=both, 1=male, 2=female (Athena); remapped below
    "hunter_type": 3,  # 0=both, 1=blade, 2=gunner
    "rarity": 4,
    "slots": 5,  # integer 0–3
    "hr": 6,
    "village": 7,
    "defense": 8,
    "max_defense": 9,
    "res_fire": 10,
    "res_water": 11,
    "res_ice": 12,
    "res_thunder": 13,
    "res_dragon": 14,
    "skill_start": 15,  # 5 x (tree name, points)
    "skill_pairs": 5,
}

# Name-only, matching ArmorExists (`Armor.cpp:10-16`).
ARMOR_DEDUP = "name"

# --- decorations.txt ---

DECORATION = {
    "name": 0,
    "name_ja": 1,
    "rarity": 2,
    "slots": 3,
    "hr": 4,
    "village": 5,
    "skill1_tree": 6,
    "skill1_points": 7,
    "skill2_tree": 8,
    "skill2_points": 9,
}

# --- skills.txt (tabular; later rows omit tag/order) ---

SKILLS = {
    "name_en": 0,
    "name_ja": 1,
    "tree_en": 2,  # empty → Torso Inc marker
    "tree_ja": 3,
    "points": 4,
    "tag": 6,
    "order": 7,
}

TORSO_INC_TREE = "Torso Inc"

# Athena Languages/English (TMO) — Team Maverick One fan names (ADR 0009).
ENGLISH_LOCALE_DIR = "Languages/English (TMO)"
DUMMY_MARK = "(dummy)"

# Athena 0/1/2 → schema 0=male/blade, 1=female/gunner, 2=both
_ATHENA_GENDER = {"1": 0, "2": 1}  # else both
_ATHENA_TYPE = {"1": 0, "2": 1}


def parse_slots(raw: str) -> int:
    return int(raw.strip())


def parse_level_requirement(raw: str) -> int:
    return int(raw.strip())


def parse_gender(raw: str) -> int:
    return _ATHENA_GENDER.get(raw.strip(), 2)


def parse_hunter_type(raw: str) -> int:
    return _ATHENA_TYPE.get(raw.strip(), 2)
