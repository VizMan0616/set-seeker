"""skill_tree_tags, skill_categories, armor_pieces.is_dummy

Athena skill trees can carry several filter tags; dummy pieces are flagged
from the English overlay name (Armor.cpp:39). Fresh installs already get
these from MetaData.create_all (0001); this migration is a guarded ALTER
for existing databases.

Revision ID: 0003_skill_tags_and_dummy
Revises: 0002_decoration_village_stars
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_skill_tags_and_dummy"
down_revision: str | None = "0002_decoration_village_stars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "skill_tree_tags" not in tables:
        op.create_table(
            "skill_tree_tags",
            sa.Column("tree_id", sa.Integer(), sa.ForeignKey("skill_trees.id"), primary_key=True),
            sa.Column("tag", sa.String(32), primary_key=True),
        )
    if "skill_categories" not in tables:
        op.create_table(
            "skill_categories",
            sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), primary_key=True),
            sa.Column("tag", sa.String(32), primary_key=True),
            sa.Column("sort_order", sa.Integer(), nullable=False),
        )
    armor_cols = {c["name"] for c in inspector.get_columns("armor_pieces")}
    if "is_dummy" not in armor_cols:
        op.add_column(
            "armor_pieces",
            sa.Column("is_dummy", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    armor_cols = {c["name"] for c in inspector.get_columns("armor_pieces")}
    if "is_dummy" in armor_cols:
        op.drop_column("armor_pieces", "is_dummy")
    if "skill_categories" in tables:
        op.drop_table("skill_categories")
    if "skill_tree_tags" in tables:
        op.drop_table("skill_tree_tags")
