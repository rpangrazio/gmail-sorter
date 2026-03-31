"""
SQLite backend for Gmail AI Sorter state management.

Uses the Python standard-library ``sqlite3`` module — no extra dependency
required.  The database contains a single-row ``app_state`` table that
acts as a typed key-value store for the two persisted values.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .base import BaseStateManager

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS app_state (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    history_id       TEXT,
    watch_expiry_ms  INTEGER
);
"""

_INSERT_SINGLETON = """
INSERT INTO app_state (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;
"""


class SqliteStateManager(BaseStateManager):
    """
    State manager backed by a local SQLite database file.

    The database is initialised automatically on first use.  A single
    row (``id = 1``) acts as the singleton state record.

    Args:
        db_path: Filesystem path to the SQLite database file.  The parent
            directory is created automatically if it does not exist.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # History ID
    # ------------------------------------------------------------------

    def get_history_id(self) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT history_id FROM app_state WHERE id = 1"
            ).fetchone()
        return row[0] if row else None

    def set_history_id(self, history_id: str) -> None:
        current = self.get_history_id()
        if history_id == current:
            return  # No change; skip write
        logger.debug("Updating history ID: %s → %s", current, history_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE app_state SET history_id = ? WHERE id = 1",
                (history_id,),
            )

    # ------------------------------------------------------------------
    # Watch expiry
    # ------------------------------------------------------------------

    def get_watch_expiry(self) -> Optional[datetime]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT watch_expiry_ms FROM app_state WHERE id = 1"
            ).fetchone()
        ms = row[0] if row else None
        if ms is None:
            return None
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc)

    def set_watch_expiry(self, expiry_ms: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE app_state SET watch_expiry_ms = ? WHERE id = 1",
                (expiry_ms,),
            )
        expiry_dt = datetime.fromtimestamp(expiry_ms / 1000.0, tz=timezone.utc)
        logger.debug("Watch expiry updated to %s", expiry_dt.isoformat())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a new connection with autocommit-style context manager."""
        conn = sqlite3.connect(self._db_path)
        conn.isolation_level = None  # autocommit; explicit transactions via BEGIN
        return conn

    def _init_db(self) -> None:
        """Create the table and the singleton row if they do not exist."""
        with self._connect() as conn:
            conn.execute("BEGIN")
            conn.execute(_DDL)
            conn.execute(_INSERT_SINGLETON)
            conn.execute("COMMIT")
        logger.debug("SQLite state database ready at %s", self._db_path)
