"""session/search id columns as String(32) for MariaDB PK/FK support

MariaDB rejects TEXT/BLOB primary keys without a prefix length. Session and
search ids are uuid4().hex (32 chars). Fresh installs get String columns from
0001 MetaData; this migration alters existing TEXT columns in place.

Revision ID: 0004_session_id_string_pk
Revises: 0003_skill_tags_and_dummy
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_session_id_string_pk"
down_revision: str | None = "0003_skill_tags_and_dummy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _needs_alter(inspector: sa.Inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    for col in inspector.get_columns(table):
        if col["name"] != column:
            continue
        col_type = col["type"]
        if isinstance(col_type, sa.String) and getattr(col_type, "length", None) == 32:
            return False
        return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    alters = [
        ("sessions", "id"),
        ("user_charms", "session_id"),
        ("search_states", "id"),
        ("search_states", "session_id"),
    ]
    for table, column in alters:
        if not _needs_alter(inspector, table, column):
            continue
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                column,
                existing_type=sa.Text(),
                type_=sa.String(32),
                existing_nullable=False,
                nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    alters = [
        ("search_states", "session_id"),
        ("search_states", "id"),
        ("user_charms", "session_id"),
        ("sessions", "id"),
    ]
    for table, column in alters:
        if table not in inspector.get_table_names():
            continue
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                column,
                existing_type=sa.String(32),
                type_=sa.Text(),
                existing_nullable=False,
                nullable=False,
            )
