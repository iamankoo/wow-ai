"""Model/metadata tests that don't require a live database connection."""

from app.db.base import Base
from app import models  # noqa: F401  (imports all models, populating metadata)


EXPECTED_TABLES = {
    "users",
    "contacts",
    "context_profiles",
    "calls",
    "conversations",
    "transcript_segments",
    "summaries",
    "memories",
    "agent_states",
    "feedback_events",
}


def test_all_domain_tables_are_registered():
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables.keys()))


def test_contact_has_user_foreign_key():
    contact_table = Base.metadata.tables["contacts"]
    fk_targets = {fk.target_fullname for fk in contact_table.foreign_keys}
    assert "users.id" in fk_targets


def test_memory_table_has_embedding_column():
    memory_table = Base.metadata.tables["memories"]
    assert "embedding" in memory_table.columns


def test_memory_table_has_safety_columns():
    """See docs "Memory safety": memory_type/status/confidence differentiate
    observed vs. confirmed facts, deleted_at supports user-initiated
    deletion without losing the audit trail."""
    memory_table = Base.metadata.tables["memories"]
    assert {"memory_type", "status", "confidence", "deleted_at"}.issubset(
        set(memory_table.columns.keys())
    )

