"""MHFU column map — positional parsing for the gen-2 data files ONLY.

Never reuse these positions for another pack (run-etl rule 1). Derived from the
legacy parsers, cited by file:line against sources/MHFU-ASS @ 134acee8:

- Armor:   `MH Armor/Armor.cpp:36-83`    (2 header lines, `O--` slot notation)
- Decor.:  `MH Armor/Decoration.cpp:55-108` (no header; points BEFORE tree name)
- Level reqs (`6!`, `5!8`): `MH Armor/Common.cpp:45-58`
- Slot notation:           `MH Armor/Common.cpp:60-73`
"""

# --- armor CSV (head/body/arms/waist/legs.csv), 32 fields per row ---

ARMOR = {
    "name": 0,
    # 1 = price (zenny string, not stored); 2-9 = 4x (material, amount), not stored
    "defense": 10,
    "res_fire": 11,
    "res_thunder": 12,
    "res_dragon": 13,
    "res_water": 14,
    "res_ice": 15,
    "gender": 16,  # "Male" | "Female" | "Male/ Female" (spacing varies per file)
    "hunter_type": 17,  # "Blade" | "Gunner" | "Blade/ Gunner" (spacing varies)
    "rarity": 18,
    "hr": 19,  # level-req syntax, see parse_level_requirement
    "village": 20,  # "Elder*" column, same syntax
    "slots": 21,  # "---" | "O--" | "OO-" | "OOO"
    "skill_start": 22,  # 5 x (tree name, points)
    "skill_pairs": 5,
}

# --- decorations CSV (no header), 25 fields per row ---

DECORATION = {
    "name": 0,
    # 1 = price, not stored
    "slots": 2,  # same O-- notation; count = decoration size 1..3
    "hr": 3,
    "village": 4,  # elder-star req (decorations.village_stars, migration 0002)
    "skill1_points": 5,  # NOTE: points first, then tree name (inverse of armor)
    "skill1_tree": 6,
    "skill2_points": 7,
    "skill2_tree": 8,
    # 9-24 = 2 x 4x (qty, material) craft components, not stored
}

# Armor pieces listing this tree carry the torso_inc flag instead of a skill row
# (legacy: `Armor.cpp:80-81`; the tree's own block in skills.txt has no thresholds).
TORSO_INC_TREE = "Torso Inc"

GENDER = {"male": 0, "female": 1}  # anything else -> 2 (both)
HUNTER_TYPE = {"blade": 0, "gunner": 1}  # anything else -> 2 (both)


def parse_slots(notation: str) -> int:
    """`O--` notation -> integer slot count (`Common.cpp:67-73`)."""
    return notation.count("O")


def parse_level_requirement(raw: str) -> int:
    """Collapse the legacy available/required pair into one progression threshold.

    Legacy keeps two numbers (`Common.cpp:45-58`): `"6"` = available at rank 6,
    `"6!"` = hard-requires rank 6, `"5!8"` = requires 5 / available at 8. The
    set-seeker schema has a single `hr_required` / `village_stars` column, so we
    store the most conservative (max) of the pair.
    """
    text = raw.strip().strip('"')
    req, bang, avail = text.partition("!")
    if bang:
        return max(int(req), int(avail) if avail else 0)
    return int(text)


def parse_gender(raw: str) -> int:
    return GENDER.get(raw.strip().lower(), 2)


def parse_hunter_type(raw: str) -> int:
    return HUNTER_TYPE.get(raw.strip().lower(), 2)


# Official English overlay (`LoadedData::LoadLanguage`). CSV `name` columns follow
# the TeamHGG P2G fan pack; set-seeker stores Languages/English MHFU instead.
# Dummy detection still uses overlay names that contain `(dummy)` (`Armor.cpp:39`).
ENGLISH_LOCALE_DIR = "Languages/English MHFU"
DUMMY_MARK = "(dummy)"
