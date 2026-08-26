"""decorations.village_stars — second progression path for jewels

Legacy decorations.csv carries both an HR and an elder-star requirement
(`Decoration.cpp:55-108`); 0001 kept only HR, which made village-only jewels
(Artisan Jewel, Razor Jewel) vanish from HR-capped searches. Fresh installs
already get the column from 0001 (it applies the current MetaData), so this
migration is a guarded no-op there and an ALTER for existing databases.

Revision ID: 0002_decoration_village_stars
Revises: 0001_initial
Create Date: 2026-08-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_decoration_village_stars"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("decorations")}
    if "village_stars" not in existing:
        op.add_column(
            "decorations",
            sa.Column("village_stars", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("decorations")}
    if "village_stars" in existing:
        op.drop_column("decorations", "village_stars")
