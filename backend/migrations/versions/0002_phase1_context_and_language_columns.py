"""add context_profiles.user_instructions and transcript_segments.language

Revision ID: 0002_phase1_cols
Revises: 0001_baseline
Create Date: 2026-10-01

Both columns were added to the models after the last deployed schema and
`create_all` never alters existing tables, so deploying the current code to
an existing database (production Neon) would fail on the first query that
selects them. Both are nullable with no default - existing rows are
untouched.
"""

import sqlalchemy as sa

from app.db.migration_helpers import add_column_if_missing, drop_column_if_present

revision = "0002_phase1_cols"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing("context_profiles", sa.Column("user_instructions", sa.Text(), nullable=True))
    add_column_if_missing("transcript_segments", sa.Column("language", sa.String(16), nullable=True))


def downgrade() -> None:
    drop_column_if_present("transcript_segments", "language")
    drop_column_if_present("context_profiles", "user_instructions")
