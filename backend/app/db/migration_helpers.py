"""Idempotent DDL helpers for revisions: a column may already exist (a fresh
database is built from the current models by the baseline) or already be
gone, so every schema change checks first instead of assuming."""

import sqlalchemy as sa
from alembic import op


def has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {c["name"] for c in inspector.get_columns(table)}


def add_column_if_missing(table: str, column: sa.Column) -> None:
    if not has_column(table, column.name):
        op.add_column(table, column)


def drop_column_if_present(table: str, column: str) -> None:
    if has_column(table, column):
        op.drop_column(table, column)
