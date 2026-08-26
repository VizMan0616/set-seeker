"""initial schema (docs/specs/database-schema.md)

The schema is defined once in app.repository.tables; this migration applies
that same MetaData so DDL and the repository layer can never drift apart.
ETL rebuilds game-data tables via downgrade/upgrade of this migration.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-25

"""

from collections.abc import Sequence

from alembic import op
from app.repository.tables import metadata

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind())
