"""
JSON-file backend for Gmail AI Sorter state management.

State is written atomically to a single JSON file using a temp-file +
rename strategy so the file is never left in a partially-written state
if the process is killed mid-write.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .base import BaseStateManager

logger = logging.getLogger(__name__)


class JsonStateManager(BaseStateManager):
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
        return self._state.get("history_id")

    def set_history_id(self, history_id: str) -> None:
        if history_id == self._state.get("history_id"):
            return  # No change; skip disk write
        logger.debug(
            "Updating persisted history ID: %s → %s",
            self._state.get("history_id"),
            history_id,
        )
        self._state["history_id"] = history_id
        self._save()

    # ------------------------------------------------------------------
    # Watch expiry
    # ------------------------------------------------------------------

    def get_watch_expiry(self) -> Optional[datetime]:
        ms = self._state.get("watch_expiry_ms")
        if ms is None:
            return None
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc)

    def set_watch_expiry(self, expiry_ms: int) -> None:
        self._state["watch_expiry_ms"] = expiry_ms
        self._save()
        expiry_dt = datetime.fromtimestamp(expiry_ms / 1000.0, tz=timezone.utc)
        logger.debug("Watch expiry updated to %s", expiry_dt.isoformat())

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
            logger.warning(
                "Failed to read state file (%s); starting with empty state.", exc
            )
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
