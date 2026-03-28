"""
Persistent state management for Gmail AI Sorter.

Stores the Gmail history cursor (historyId) and the Gmail watch expiry
timestamp between runs.  State is written atomically to prevent corruption
if the container is stopped mid-write.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class StateManager:
    """
    Reads and writes application state to a JSON file.

    State file schema::

        {
            "history_id": "12345678",
            "watch_expiry_ms": 1711616400000
        }

    The file is written atomically: new content is first written to a
    sibling temp file, then renamed over the target.  On most filesystems
    this is an atomic operation that prevents a partially written state file.

    Args:
        state_file_path: Path to the JSON state file.  The parent directory
            is created automatically on first write.
    """

    def __init__(self, state_file_path: str) -> None:
        self._path = Path(state_file_path)
        self._state: dict = self._load()

    # ------------------------------------------------------------------
    # History ID
    # ------------------------------------------------------------------

    def get_history_id(self) -> Optional[str]:
        """
        Return the last known Gmail history ID, or None if not yet set.

        The history ID is used as the *startHistoryId* parameter when calling
        ``users.history.list()`` to fetch only changes since the last poll.
        """
        return self._state.get("history_id")

    def set_history_id(self, history_id: str) -> None:
        """
        Persist a new history ID to disk.

        Args:
            history_id: The new history ID string from the Gmail API.
        """
        if history_id == self._state.get("history_id"):
            return  # No change; skip disk write
        logger.debug("Updating persisted history ID: %s → %s",
                     self._state.get("history_id"), history_id)
        self._state["history_id"] = history_id
        self._save()

    # ------------------------------------------------------------------
    # Watch expiry
    # ------------------------------------------------------------------

    def get_watch_expiry(self) -> Optional[datetime]:
        """
        Return the Gmail watch expiry as a timezone-aware UTC datetime, or None.
        """
        ms = self._state.get("watch_expiry_ms")
        if ms is None:
            return None
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc)

    def set_watch_expiry(self, expiry_ms: int) -> None:
        """
        Persist the Gmail watch expiry timestamp.

        Args:
            expiry_ms: Expiry time as a Unix timestamp in milliseconds,
                as returned by the ``users.watch()`` response.
        """
        self._state["watch_expiry_ms"] = expiry_ms
        self._save()
        expiry_dt = datetime.fromtimestamp(expiry_ms / 1000.0, tz=timezone.utc)
        logger.debug("Watch expiry updated to %s", expiry_dt.isoformat())

    def is_watch_expiring_soon(self, buffer_hours: int = 24) -> bool:
        """
        Return True if the Gmail watch will expire within *buffer_hours*.

        Gmail watch registrations last 7 days.  Renewing with a 24-hour buffer
        ensures there is no gap in notifications if the container restarts.

        Args:
            buffer_hours: Renewal window in hours before actual expiry.
        """
        expiry = self.get_watch_expiry()
        if expiry is None:
            return True  # Not yet set; must register a watch
        now = datetime.now(tz=timezone.utc)
        from datetime import timedelta
        return (expiry - now) < timedelta(hours=buffer_hours)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        """Read the state file from disk, returning an empty dict on failure."""
        if not self._path.exists():
            logger.debug("No state file found at %s; starting fresh.", self._path)
            return {}
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
            logger.debug("State loaded from %s: %s", self._path, data)
            return data if isinstance(data, dict) else {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read state file (%s); starting with empty state.", exc)
            return {}

    def _save(self) -> None:
        """
        Write the current state to disk atomically.

        Uses a temp file + rename so the state file is never left in a
        partially-written state if the process is killed mid-write.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=".state_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._state, f, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
