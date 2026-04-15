"""Unit tests for SQLite database repository behavior."""

from __future__ import annotations

from datetime import datetime

from gmail_sorter.db.repository import (
    BackfillState,
    ClassificationRecord,
    Database,
    DlqEntry,
)


def build_record(message_id: str, category: str = "marketing") -> ClassificationRecord:
    """Create a classification record fixture payload."""

    return ClassificationRecord(
        message_id=message_id,
        gmail_thread_id="thread-1",
        timestamp="2026-04-15T00:00:00Z",
        category=category,
        confidence=0.91,
        model_used="gpt-4o",
        prompt_template_hash="hash-123",
        label_applied="AutoSort/Marketing",
        processing_duration_ms=42,
    )


def test_initialize_creates_tables() -> None:
    """Database initialization creates all required tables."""

    db = Database(":memory:")
    db.initialize()

    table_names = {
        row["name"]
        for row in db._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    assert "classifications" in table_names
    assert "backfill_state" in table_names
    assert "dead_letter_queue" in table_names


def test_upsert_classification_keeps_single_row_per_message_id() -> None:
    """Upserting the same message ID twice preserves idempotent single-row state."""

    db = Database(":memory:")
    db.initialize()

    first = build_record("msg-1", category="marketing")
    second = build_record("msg-1", category="billing")
    second.label_applied = "AutoSort/Billing"

    db.upsert_classification(first)
    db.upsert_classification(second)

    count = db._connection.execute(
        "SELECT COUNT(*) AS count FROM classifications WHERE message_id = ?",
        ("msg-1",),
    ).fetchone()["count"]

    stored = db.get_classification("msg-1")

    assert count == 1
    assert stored is not None
    assert stored.category == "billing"


def test_is_classified_reflects_insert_state() -> None:
    """Classification existence checks should reflect persisted state."""

    db = Database(":memory:")
    db.initialize()

    assert db.is_classified("msg-1") is False

    db.upsert_classification(build_record("msg-1"))

    assert db.is_classified("msg-1") is True


def test_add_to_dlq_and_get_dlq_entries_round_trip() -> None:
    """Dead-letter entries should be persisted and returned."""

    db = Database(":memory:")
    db.initialize()

    entry = DlqEntry(
        id=None,
        message_id="msg-dlq-1",
        error_type="llm_error",
        error_message="request timeout",
        attempts=3,
    )

    db.add_to_dlq(entry)
    entries = db.get_dlq_entries(limit=10)

    assert len(entries) == 1
    assert entries[0].message_id == "msg-dlq-1"
    assert entries[0].error_type == "llm_error"
    assert entries[0].attempts == 3


def test_backfill_state_round_trip() -> None:
    """Backfill state upsert and retrieval should round-trip values."""

    db = Database(":memory:")
    db.initialize()

    state = BackfillState(
        id=None,
        last_page_token="token-1",
        last_message_id="msg-99",
        status="running",
        started_at="2026-04-15T00:00:00Z",
        completed_at=None,
        total_processed=100,
        total_skipped=5,
    )

    db.upsert_backfill_state(state)
    latest = db.get_latest_backfill_state()

    assert latest is not None
    assert latest.last_page_token == "token-1"
    assert latest.last_message_id == "msg-99"
    assert latest.status == "running"
    assert latest.total_processed == 100
    assert latest.total_skipped == 5


def test_get_stats_returns_total_and_breakdown() -> None:
    """Stats should provide total and per-category counts."""

    db = Database(":memory:")
    db.initialize()

    db.upsert_classification(build_record("msg-1", category="marketing"))
    db.upsert_classification(build_record("msg-2", category="billing"))
    db.upsert_classification(build_record("msg-3", category="marketing"))

    stats = db.get_stats(since=datetime(2026, 4, 14, 0, 0, 0))

    assert stats["total_processed"] == 3
    assert stats["by_category"]["marketing"] == 2
    assert stats["by_category"]["billing"] == 1
