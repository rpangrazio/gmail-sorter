"""SQLite schema definitions for local persistence.

This module stores the full schema used by the Gmail Sorting System.
"""

SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS classifications (
    message_id          TEXT PRIMARY KEY,
    gmail_thread_id     TEXT NOT NULL,
    timestamp           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    category            TEXT NOT NULL,
    confidence          REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    model_used          TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    label_applied       TEXT NOT NULL,
    processing_duration_ms INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_classifications_timestamp ON classifications(timestamp);
CREATE INDEX IF NOT EXISTS idx_classifications_category ON classifications(category);

CREATE TABLE IF NOT EXISTS backfill_state (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    last_page_token     TEXT,
    last_message_id     TEXT,
    status              TEXT NOT NULL CHECK (status IN ('running', 'completed', 'interrupted'))
                        DEFAULT 'running',
    started_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at        TEXT,
    total_processed     INTEGER NOT NULL DEFAULT 0,
    total_skipped       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id          TEXT NOT NULL,
    error_type          TEXT NOT NULL,
    error_message       TEXT NOT NULL,
    attempts            INTEGER NOT NULL DEFAULT 0,
    first_failed_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_failed_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_dlq_message_id ON dead_letter_queue(message_id);
CREATE INDEX IF NOT EXISTS idx_dlq_error_type ON dead_letter_queue(error_type);
"""
