"""SQLite repository implementation for Gmail Sorting System."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from gmail_sorter.db.schema import SCHEMA_SQL


@dataclass(slots=True)
class ClassificationRecord:
    """Classification table row representation."""

    message_id: str
    gmail_thread_id: str
    timestamp: str
    category: str
    confidence: float
    model_used: str
    prompt_template_hash: str
    label_applied: str
    processing_duration_ms: int = 0


@dataclass(slots=True)
class BackfillState:
    """Backfill state table row representation."""

    id: int | None
    last_page_token: str | None
    last_message_id: str | None
    status: str
    started_at: str | None
    completed_at: str | None
    total_processed: int = 0
    total_skipped: int = 0


@dataclass(slots=True)
class DlqEntry:
    """Dead-letter queue table row representation."""

    id: int | None
    message_id: str
    error_type: str
    error_message: str
    attempts: int = 0
    first_failed_at: str | None = None
    last_failed_at: str | None = None


class Database:
    """SQLite-backed repository for classifications and processing state."""

    def __init__(self, path: str) -> None:
        """Create a database connection.

        Args:
            path: SQLite database path. Use ``":memory:"`` for tests.
        """

        self._path = path
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        """Create all required tables and indexes if missing."""

        self._connection.executescript(SCHEMA_SQL)
        self._connection.commit()

    def close(self) -> None:
        """Close the active SQLite connection."""

        self._connection.close()

    def upsert_classification(self, record: ClassificationRecord) -> None:
        """Insert or replace a classification row by message ID."""

        query = """
        INSERT OR REPLACE INTO classifications (
            message_id,
            gmail_thread_id,
            timestamp,
            category,
            confidence,
            model_used,
            prompt_template_hash,
            label_applied,
            processing_duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self._connection.execute(
            query,
            (
                record.message_id,
                record.gmail_thread_id,
                record.timestamp,
                record.category,
                record.confidence,
                record.model_used,
                record.prompt_template_hash,
                record.label_applied,
                record.processing_duration_ms,
            ),
        )
        self._connection.commit()

    def get_classification(self, message_id: str) -> ClassificationRecord | None:
        """Fetch a classification row by message ID."""

        cursor = self._connection.execute(
            """
            SELECT
                message_id,
                gmail_thread_id,
                timestamp,
                category,
                confidence,
                model_used,
                prompt_template_hash,
                label_applied,
                processing_duration_ms
            FROM classifications
            WHERE message_id = ?
            """,
            (message_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return ClassificationRecord(
            message_id=row["message_id"],
            gmail_thread_id=row["gmail_thread_id"],
            timestamp=row["timestamp"],
            category=row["category"],
            confidence=row["confidence"],
            model_used=row["model_used"],
            prompt_template_hash=row["prompt_template_hash"],
            label_applied=row["label_applied"],
            processing_duration_ms=row["processing_duration_ms"],
        )

    def is_classified(self, message_id: str) -> bool:
        """Return whether a message already has a classification record."""

        cursor = self._connection.execute(
            "SELECT 1 FROM classifications WHERE message_id = ? LIMIT 1",
            (message_id,),
        )
        return cursor.fetchone() is not None

    def get_stats(self, since: datetime | None = None) -> dict[str, Any]:
        """Return aggregate classification statistics.

        Args:
            since: Optional UTC timestamp lower bound for filtered stats.
        """

        filter_clause = ""
        params: tuple[Any, ...] = ()
        if since is not None:
            filter_clause = "WHERE timestamp >= ?"
            params = (since.strftime("%Y-%m-%dT%H:%M:%SZ"),)

        total_cursor = self._connection.execute(
            f"SELECT COUNT(*) AS count FROM classifications {filter_clause}",
            params,
        )
        total_processed = total_cursor.fetchone()["count"]

        breakdown_cursor = self._connection.execute(
            f"""
            SELECT category, COUNT(*) AS count
            FROM classifications
            {filter_clause}
            GROUP BY category
            ORDER BY count DESC, category ASC
            """,
            params,
        )
        by_category = {
            row["category"]: row["count"]
            for row in breakdown_cursor.fetchall()
        }

        return {
            "total_processed": total_processed,
            "by_category": by_category,
            "since": since.strftime("%Y-%m-%dT%H:%M:%SZ") if since else None,
        }

    def upsert_backfill_state(self, state: BackfillState) -> None:
        """Insert or update the current backfill state row."""

        if state.id is None:
            cursor = self._connection.execute(
                """
                INSERT INTO backfill_state (
                    last_page_token,
                    last_message_id,
                    status,
                    started_at,
                    completed_at,
                    total_processed,
                    total_skipped
                ) VALUES (?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')), ?, ?, ?)
                """,
                (
                    state.last_page_token,
                    state.last_message_id,
                    state.status,
                    state.started_at,
                    state.completed_at,
                    state.total_processed,
                    state.total_skipped,
                ),
            )
            self._connection.commit()
            state.id = int(cursor.lastrowid)
            return

        self._connection.execute(
            """
            UPDATE backfill_state
            SET
                last_page_token = ?,
                last_message_id = ?,
                status = ?,
                started_at = COALESCE(?, started_at),
                completed_at = ?,
                total_processed = ?,
                total_skipped = ?
            WHERE id = ?
            """,
            (
                state.last_page_token,
                state.last_message_id,
                state.status,
                state.started_at,
                state.completed_at,
                state.total_processed,
                state.total_skipped,
                state.id,
            ),
        )
        self._connection.commit()

    def get_latest_backfill_state(self) -> BackfillState | None:
        """Return the most recently inserted backfill state row."""

        cursor = self._connection.execute(
            """
            SELECT
                id,
                last_page_token,
                last_message_id,
                status,
                started_at,
                completed_at,
                total_processed,
                total_skipped
            FROM backfill_state
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return BackfillState(
            id=row["id"],
            last_page_token=row["last_page_token"],
            last_message_id=row["last_message_id"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            total_processed=row["total_processed"],
            total_skipped=row["total_skipped"],
        )

    def add_to_dlq(self, entry: DlqEntry) -> None:
        """Insert a dead-letter queue row."""

        cursor = self._connection.execute(
            """
            INSERT INTO dead_letter_queue (
                message_id,
                error_type,
                error_message,
                attempts,
                first_failed_at,
                last_failed_at
            ) VALUES (
                ?,
                ?,
                ?,
                ?,
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
            """,
            (
                entry.message_id,
                entry.error_type,
                entry.error_message,
                entry.attempts,
                entry.first_failed_at,
                entry.last_failed_at,
            ),
        )
        self._connection.commit()
        entry.id = int(cursor.lastrowid)

    def get_dlq_entries(self, limit: int = 100) -> list[DlqEntry]:
        """Return recent dead-letter queue entries."""

        cursor = self._connection.execute(
            """
            SELECT
                id,
                message_id,
                error_type,
                error_message,
                attempts,
                first_failed_at,
                last_failed_at
            FROM dead_letter_queue
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )

        return [
            DlqEntry(
                id=row["id"],
                message_id=row["message_id"],
                error_type=row["error_type"],
                error_message=row["error_message"],
                attempts=row["attempts"],
                first_failed_at=row["first_failed_at"],
                last_failed_at=row["last_failed_at"],
            )
            for row in cursor.fetchall()
        ]
