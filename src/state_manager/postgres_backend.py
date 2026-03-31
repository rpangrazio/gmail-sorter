"""
PostgreSQL backend for Gmail AI Sorter state management.

Uses ``psycopg2`` to connect to a PostgreSQL server.  The connection is
configured via a libpq-compatible DSN or connection URL, typically passed
through the ``DATABASE_URL`` environment variable.

The database schema mirrors the SQLite backend: a single ``app_state`` table
with one row (``id = 1``) that stores the two persisted values.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "psycopg2 is required for the PostgreSQL state backend. "
        "Install it with: pip install psycopg2-binary"
    ) from exc

from .base import BaseStateManager

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS app_state (
    id               INTEGER PRIMARY KEY,
    history_id       TEXT,
    watch_expiry_ms  BIGINT
);
"""

_INSERT_SINGLETON = """
INSERT INTO app_state (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;
"""


class PostgresStateManager(BaseStateManager):
    """
    State manager backed by a PostgreSQL database.

    A new connection is opened for every read/write operation so there are
    no long-lived idle connections.  For the low-frequency writes performed
    by this application the overhead is negligible.

    Args:
        dsn: A libpq connection string or ``postgresql://`` URL.
            Example: ``"postgresql://user:pass@localhost:5432/gmail_sorter"``
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._init_db()

    # ------------------------------------------------------------------
    # History ID
    # ------------------------------------------------------------------

    def get_history_id(self) -> Optional[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT history_id FROM app_state WHERE id = 1")
                row = cur.fetchone()
        return row[0] if row else None

    def set_history_id(self, history_id: str) -> None:
        current = self.get_history_id()
        if history_id == current:
            return  # No change; skip write
        logger.debug("Updating history ID: %s → %s", current, history_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE app_state SET history_id = %s WHERE id = 1",
                    (history_id,),
                )

    # ------------------------------------------------------------------
    # Watch expiry
    # ------------------------------------------------------------------

    def get_watch_expiry(self) -> Optional[datetime]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT watch_expiry_ms FROM app_state WHERE id = 1"
                )
                row = cur.fetchone()
        ms = row[0] if row else None
        if ms is None:
            return None
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc)

    def set_watch_expiry(self, expiry_ms: int) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE app_state SET watch_expiry_ms = %s WHERE id = 1",
                    (expiry_ms,),
                )
        expiry_dt = datetime.fromtimestamp(expiry_ms / 1000.0, tz=timezone.utc)
        logger.debug("Watch expiry updated to %s", expiry_dt.isoformat())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _connect(self):
        """Open a new psycopg2 connection."""
        return psycopg2.connect(self._dsn)

    def _init_db(self) -> None:
        """Create the table and the singleton row if they do not exist."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_DDL)
                cur.execute(_INSERT_SINGLETON)
        logger.debug("PostgreSQL app_state table ready.")
