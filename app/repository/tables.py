"""Single source of truth for the schema (docs/specs/database-schema.md).

Both the repositories and the Alembic initial migration build on this MetaData,
so the migration cannot drift from the table objects. Portable column types
only — the MariaDB swap must stay a config change (ADR 0004).
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

# --- Game data (ETL-owned, read-only at runtime) ---

games = Table(
    "games",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(8), nullable=False, unique=True),
    Column("name", String(64), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("features", Text, nullable=False),
)

skill_trees = Table(
    "skill_trees",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=False),
    Column("name_en", String(64), nullable=False),
    Column("name_ja", String(64)),
    Column("category_tag", String(32)),
)

skills = Table(
    "skills",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tree_id", Integer, ForeignKey("skill_trees.id"), nullable=False),
    Column("name_en", String(64), nullable=False),
    Column("name_ja", String(64)),
    Column("points", Integer, nullable=False),
    Column("is_negative", Boolean, nullable=False, default=False),
    Index("ix_skills_tree_points", "tree_id", "points"),
)

armor_pieces = Table(
    "armor_pieces",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=False),
    Column("slot", Integer, nullable=False),  # 0=head 1=body 2=arms 3=waist 4=legs
    Column("name_en", String(96), nullable=False),
    Column("name_ja", String(96)),
    Column("rarity", Integer, nullable=False),
    Column("slots", Integer, nullable=False),
    Column("gender", Integer, nullable=False),  # 0=m 1=f 2=both
    Column("hunter_type", Integer, nullable=False),  # 0=blade 1=gun 2=both
    Column("hr_required", Integer, nullable=False, default=0),
    Column("village_stars", Integer, nullable=False, default=0),
    Column("defense", Integer, nullable=False),
    Column("max_defense", Integer, nullable=False),
    Column("res_fire", Integer, nullable=False),
    Column("res_water", Integer, nullable=False),
    Column("res_ice", Integer, nullable=False),
    Column("res_thunder", Integer, nullable=False),
    Column("res_dragon", Integer, nullable=False),
    Column("torso_inc", Boolean, nullable=False, default=False),
    Column("is_event", Boolean, nullable=False, default=False),
    Index("ix_armor_pieces_pruning", "game_id", "slot", "hunter_type", "gender"),
    Index("ix_armor_pieces_hr", "game_id", "hr_required"),
)

armor_skills = Table(
    "armor_skills",
    metadata,
    Column("armor_id", Integer, ForeignKey("armor_pieces.id"), primary_key=True),
    Column("tree_id", Integer, ForeignKey("skill_trees.id"), primary_key=True),
    Column("points", Integer, nullable=False),
    Index("ix_armor_skills_tree", "tree_id", "armor_id"),
)

decorations = Table(
    "decorations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=False),
    Column("name_en", String(96), nullable=False),
    Column("name_ja", String(96)),
    Column("rarity", Integer, nullable=False),
    Column("size", Integer, nullable=False),
    Column("hr_required", Integer, nullable=False, default=0),
    Column("is_event", Boolean, nullable=False, default=False),
    Index("ix_decorations_game_size", "game_id", "size"),
)

decoration_skills = Table(
    "decoration_skills",
    metadata,
    Column("decoration_id", Integer, ForeignKey("decorations.id"), primary_key=True),
    Column("tree_id", Integer, ForeignKey("skill_trees.id"), primary_key=True),
    Column("points", Integer, nullable=False),
    Index("ix_decoration_skills_tree", "tree_id", "decoration_id"),
)

charm_types = Table(
    "charm_types",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=False),
    Column("code", String(16), nullable=False),
    Column("max_slots", Integer, nullable=False),
)

charm_skill_ranges = Table(
    "charm_skill_ranges",
    metadata,
    Column("charm_type_id", Integer, ForeignKey("charm_types.id"), primary_key=True),
    Column("tree_id", Integer, ForeignKey("skill_trees.id"), primary_key=True),
    Column("skill_slot", Integer, primary_key=True),
    Column("min_points", Integer, nullable=False),
    Column("max_points", Integer, nullable=False),
    Index("ix_charm_skill_ranges_type_tree", "charm_type_id", "tree_id"),
)

charm_slot_thresholds = Table(
    "charm_slot_thresholds",
    metadata,
    Column("charm_type_id", Integer, ForeignKey("charm_types.id"), primary_key=True),
    Column("fulfillment", Integer, primary_key=True),
    Column("slots", Integer, nullable=False),
)

mh3u_charm_tables = Table(
    "mh3u_charm_tables",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=False),
    Column("table_index", Integer, nullable=False),
    Column("tree_id", Integer, ForeignKey("skill_trees.id"), nullable=False),
    Column("skill_slot", Integer, nullable=False),
    Column("max_points", Integer, nullable=False),
)

# --- User data (runtime-owned, never ETL'd) ---

sessions = Table(
    "sessions",
    metadata,
    Column("id", Text, primary_key=True),
    Column("created_at", DateTime, nullable=False),
    Column("last_seen_at", DateTime, nullable=False),
)

user_charms = Table(
    "user_charms",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", Text, ForeignKey("sessions.id"), nullable=False),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=False),
    Column("slots", Integer, nullable=False),
    Column("skill1_tree", Integer, ForeignKey("skill_trees.id")),
    Column("skill1_points", Integer),
    Column("skill2_tree", Integer, ForeignKey("skill_trees.id")),
    Column("skill2_points", Integer),
    Column("note", String(128)),
    Index("ix_user_charms_session_game", "session_id", "game_id"),
)

search_states = Table(
    "search_states",
    metadata,
    Column("id", Text, primary_key=True),
    Column("session_id", Text, ForeignKey("sessions.id"), nullable=False),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=False),
    Column("query_json", Text, nullable=False),
    Column("exclusions", Text, nullable=False, default="[]"),
    Column("created_at", DateTime, nullable=False),
    Index("ix_search_states_session_created", "session_id", "created_at"),
)
