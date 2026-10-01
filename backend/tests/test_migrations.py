"""Alembic migrations (backend/migrations): fresh create, adoption of an
existing create_all-era database WITHOUT data loss, idempotency, downgrade.

SQLite variants always run (pgvector's table is skipped there by design);
the Postgres variant - the real production dialect, with pgvector - runs
only when TEST_DATABASE_URL points at a THROWAWAY database (it drops
everything, exactly like the other DB integration tests).

These tests are deliberately synchronous: env.py drives its own event loop.
"""

import os
import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.db.base import Base
from app.models.user import User

BACKEND = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _cfg(async_url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", async_url)
    return cfg


def _sqlite(tmp_path):
    path = tmp_path / "m.db"
    return path, f"sqlite+aiosqlite:///{path}", create_engine(f"sqlite:///{path}")


def _cols(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _version(engine):
    with engine.connect() as c:
        return c.execute(text("select version_num from alembic_version")).scalar()


def test_fresh_database_is_built_at_head(tmp_path):
    _, url, engine = _sqlite(tmp_path)
    command.upgrade(_cfg(url), "head")
    assert _version(engine) == "0002_phase1_cols"
    assert "user_instructions" in _cols(engine, "context_profiles")
    assert "language" in _cols(engine, "transcript_segments")
    assert {"users", "calls", "conversations"} <= set(inspect(engine).get_table_names())


def test_existing_create_all_database_is_adopted_without_losing_data(tmp_path):
    """The production situation: tables from an older create_all (lacking the
    two newer columns, no alembic_version table) must gain the columns with
    every existing row intact."""
    path, url, engine = _sqlite(tmp_path)
    tables = [t for t in Base.metadata.sorted_tables if "Vector" not in {type(c.type).__name__ for c in t.columns}]
    Base.metadata.create_all(engine, tables=tables)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE context_profiles DROP COLUMN user_instructions"))
        c.execute(text("ALTER TABLE transcript_segments DROP COLUMN language"))
        c.execute(
            User.__table__.insert().values(
                id=uuid.uuid4(), display_name="Keep Me", phone_number="+910000000000"
            )
        )
    assert "language" not in _cols(engine, "transcript_segments")
    assert "alembic_version" not in inspect(engine).get_table_names()

    command.upgrade(_cfg(url), "head")

    assert "language" in _cols(engine, "transcript_segments")
    assert "user_instructions" in _cols(engine, "context_profiles")
    with engine.connect() as c:
        assert c.execute(text("select display_name from users")).scalar() == "Keep Me"
    assert _version(engine) == "0002_phase1_cols"


def test_upgrade_is_idempotent(tmp_path):
    _, url, engine = _sqlite(tmp_path)
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # no-op, must not raise
    assert _version(engine) == "0002_phase1_cols"


def test_revision_survives_a_database_that_already_has_the_columns(tmp_path):
    """A fresh DB built by the baseline already has the 0002 columns - the
    guarded helpers must make 0002 a no-op rather than 'duplicate column'."""
    _, url, engine = _sqlite(tmp_path)
    cfg = _cfg(url)
    command.upgrade(cfg, "0001_baseline")
    assert "language" in _cols(engine, "transcript_segments")  # baseline used current models
    command.upgrade(cfg, "head")


@pytest.mark.skipif(sqlite3.sqlite_version_info < (3, 35), reason="needs ALTER TABLE DROP COLUMN")
def test_downgrade_of_the_latest_revision_removes_only_its_columns(tmp_path):
    _, url, engine = _sqlite(tmp_path)
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0001_baseline")
    assert "language" not in _cols(engine, "transcript_segments")
    assert "user_instructions" not in _cols(engine, "context_profiles")
    assert "users" in inspect(engine).get_table_names()  # nothing else touched


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set (needs real Postgres+pgvector)")
def test_postgres_fresh_and_adoption_paths():
    cfg = _cfg(TEST_DATABASE_URL)

    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    async def _reset():
        eng = create_async_engine(TEST_DATABASE_URL)
        async with eng.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await eng.dispose()

    async def _legacy_shape():
        """create_all, then strip the two newer columns: an old production DB."""
        eng = create_async_engine(TEST_DATABASE_URL)
        async with eng.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("ALTER TABLE context_profiles DROP COLUMN user_instructions"))
            await conn.execute(text("ALTER TABLE transcript_segments DROP COLUMN language"))
        await eng.dispose()

    async def _state():
        eng = create_async_engine(TEST_DATABASE_URL)
        async with eng.connect() as conn:
            cols = await conn.run_sync(
                lambda c: (
                    {x["name"] for x in inspect(c).get_columns("context_profiles")},
                    {x["name"] for x in inspect(c).get_columns("transcript_segments")},
                    "memories" in inspect(c).get_table_names(),
                )
            )
            ver = (await conn.execute(text("select version_num from alembic_version"))).scalar()
        await eng.dispose()
        return cols, ver

    try:
        asyncio.run(_reset())
        command.upgrade(cfg, "head")  # fresh
        (ctx, seg, has_memories), ver = asyncio.run(_state())
        assert ver == "0002_phase1_cols" and "user_instructions" in ctx and "language" in seg
        assert has_memories  # pgvector table created on the real dialect

        asyncio.run(_reset())
        asyncio.run(_legacy_shape())  # adoption of an old create_all database
        command.upgrade(cfg, "head")
        (ctx, seg, _), ver = asyncio.run(_state())
        assert ver == "0002_phase1_cols" and "user_instructions" in ctx and "language" in seg
    finally:
        asyncio.run(_reset())
