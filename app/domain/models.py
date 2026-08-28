from dataclasses import dataclass

@dataclass(frozen=True)
class SkillRequest:
    tree_id: int
    min_points: int          # activation threshold from the skills table

@dataclass(frozen=True)
class Query:
    game: str                            # pack id, e.g. "mhfu"
    skills: tuple[SkillRequest, ...]     # 1..5 entries
    weapon_slots: int                    # 0..3
    gender: str                          # "m" | "f"
    hunter_type: str                     # "blademaster" | "gunner"
    hr: int | None                       # None = uncapped
    village_stars: int | None            # None = uncapped
    allow_event: bool = False
    allow_bad_skills: bool = False
    # Athena Form1.h: chkTorsoInc defaults checked; chkDummy does not.
    allow_torso_inc: bool = True
    allow_dummy: bool = False
    # Omitted from the solver skyline (Athena Advanced Search unchecks).
    excluded_piece_ids: tuple[int, ...] = ()
    excluded_decoration_ids: tuple[int, ...] = ()
    # Dominated inf pieces forced back onto the skyline (Advanced checks).
    forced_piece_ids: tuple[int, ...] = ()
    forced_decoration_ids: tuple[int, ...] = ()
    sort: str = "defense"                # "defense" | "slots" | "rarity" | res_*
    # Expand equivalence members into separate result cards (Athena-style list).
    expand_equivalents: bool = False

@dataclass(frozen=True)
class DecorationAssignment:
    decoration_id: int
    count: int

@dataclass(frozen=True)
class ArmorSetResult:
    # Representative piece ids per slot, order: head, body, arms, waist, legs
    piece_ids: tuple[int, int, int, int, int]
    # Per-slot equivalence-class member ids (includes the representative)
    alternates: tuple[tuple[int, ...], ...]
    decorations: tuple[DecorationAssignment, ...]
    charm_id: int | None                 # always None for mhfu (pack flag talismans: false)
    active_skills: tuple[tuple[int, int], ...]   # (skill_id, points achieved)
    spare_slots: tuple[int, int, int]            # remaining size-1/2/3 slots
    defense: int

    def equivalent_count(self) -> int:
        """How many concrete sets this representative expands to."""
        n = 1
        for alts in self.alternates:
            n *= len(alts) if alts else 1
        return n

@dataclass(frozen=True)
class SearchPage:
    search_id: str
    results: tuple[ArmorSetResult, ...]  # len <= PAGE_SIZE
    partial: bool                        # solver hit its time budget
    exhausted: bool                      # no further solutions exist
    shown_count: int = 0                 # cards delivered so far (expanded when listing every set)
    remaining_count: int | None = None   # None = more exist but the tail was not counted

PAGE_SIZE = 10
