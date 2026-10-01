"""baseline: adopt-or-create the schema Base.metadata.create_all produced

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-01

Until now the schema came only from `Base.metadata.create_all` at startup,
which creates MISSING TABLES but never alters an existing one. This
baseline lets every database - a fresh one, or an existing one (e.g.
production on Neon, created by create_all) - be brought under Alembic
without touching data:

- fresh DB: creates every table (plus the pgvector extension on Postgres);
- existing DB: `checkfirst` makes it a no-op for tables that already exist.

It uses the *current* metadata, so it must NOT be edited later, and every
FUTURE revision must be written with explicit, idempotent operations (see
app/db/migration_helpers.py) - a fresh DB will already have any column a newer model
declares by the time later revisions run.

pgvector (the `memories.embedding` column) needs Postgres; on any other
dialect (SQLite, used only by some unit tests) tables holding a Vector
column are skipped.
"""

from alembic import op

from app.db.base import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _has_vector_column(table) -> bool:
    return any(type(c.type).__name__ == "Vector" for c in table.columns)


def upgrade() -> None:
    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"
    if postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    tables = [t for t in Base.metadata.sorted_tables if postgres or not _has_vector_column(t)]
    Base.metadata.create_all(bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    # Deliberately not supported: dropping every table is never a safe,
    # automatic operation for this baseline.
    raise NotImplementedError("The baseline revision cannot be downgraded.")
