"""Integration tests for SQLite repository behavior."""

from __future__ import annotations

from datetime import datetime, timezone

from gmail_sorter.db.repository import BackfillState, ClassificationRecord, Database


def test_classification_round_trip_and_upsert(tmp_path) -> None:
    """Classification records should persist and remain idempotent by message ID."""

    db_path = tmp_path / "integration.db"
    database = Database(str(db_path))
    database.initialize()

    record = ClassificationRecord(
        message_id="msg-1",
        gmail_thread_id="thread-1",
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        category="alerts",
        confidence=0.91,
        model_used="gpt-4o",
        prompt_template_hash="hash-1",
        label_applied="Label_alerts",
        processing_duration_ms=123,
    )

    database.upsert_classification(record)
    loaded = database.get_classification("msg-1")
    assert loaded is not None
    assert loaded.message_id == "msg-1"
    assert loaded.category == "alerts"

    database.upsert_classification(
        ClassificationRecord(
            message_id="msg-1",
            gmail_thread_id="thread-1",
            timestamp=record.timestamp,
            category="alerts",
            confidence=0.95,
            model_used="gpt-4o",
            prompt_template_hash="hash-2",
            label_applied="Label_alerts",
            processing_duration_ms=150,
        )
    )

    stats = database.get_stats()
    assert stats["total_processed"] == 1

    database.close()


def test_backfill_state_persists_across_reopen(tmp_path) -> None:
    """Backfill state should survive close/reopen cycles for resumability."""

    db_path = tmp_path / "integration.db"

    first = Database(str(db_path))
    first.initialize()
    first.upsert_backfill_state(
        BackfillState(
            id=None,
            last_page_token="token-2",
            last_message_id="msg-200",
            status="running",
            started_at=None,
            completed_at=None,
            total_processed=200,
            total_skipped=5,
        )
    )
    first.close()

    second = Database(str(db_path))
    second.initialize()
    latest = second.get_latest_backfill_state()

    assert latest is not None
    assert latest.last_page_token == "token-2"
    assert latest.last_message_id == "msg-200"
    assert latest.status == "running"
    assert latest.total_processed == 200
    assert latest.total_skipped == 5

    second.close()
