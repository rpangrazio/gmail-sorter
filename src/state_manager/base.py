"""
Abstract base class for Gmail AI Sorter state manager backends.

All backends must implement the four abstract methods; the
``is_watch_expiring_soon`` convenience method is provided here so
it does not have to be duplicated in every backend.
"""

import abc
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class BaseStateManager(abc.ABC):
    """
    Interface for persistent storage of two application state values:

    * **history_id** — the Gmail history cursor used as *startHistoryId*
      when calling ``users.history.list()``.
    * **watch_expiry_ms** — the Gmail watch registration expiry stored as
      a Unix timestamp in milliseconds.

    Concrete backends (JSON file, SQLite, PostgreSQL) must implement the
    four abstract methods below.
    """

    # ------------------------------------------------------------------
    # History ID
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def get_history_id(self) -> Optional[str]:
        """
        Return the last known Gmail history ID, or ``None`` if not yet set.
        """

    @abc.abstractmethod
    def set_history_id(self, history_id: str) -> None:
        """
        Persist a new history ID.

        Args:
            history_id: The new history ID string from the Gmail API.
        """

    # ------------------------------------------------------------------
    # Watch expiry
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def get_watch_expiry(self) -> Optional[datetime]:
        """
        Return the Gmail watch expiry as a timezone-aware UTC datetime,
        or ``None`` if not yet set.
        """

    @abc.abstractmethod
    def set_watch_expiry(self, expiry_ms: int) -> None:
        """
        Persist the Gmail watch expiry timestamp.

        Args:
            expiry_ms: Expiry time as a Unix timestamp in milliseconds,
                as returned by the ``users.watch()`` response.
        """

    # ------------------------------------------------------------------
    # Convenience (shared implementation)
    # ------------------------------------------------------------------

    def is_watch_expiring_soon(self, buffer_hours: int = 24) -> bool:
        """
        Return ``True`` if the Gmail watch will expire within *buffer_hours*.

        Gmail watch registrations last 7 days.  Renewing with a 24-hour
        buffer ensures there is no gap in notifications if the container
        restarts.

        Args:
            buffer_hours: Renewal window in hours before actual expiry.
        """
        expiry = self.get_watch_expiry()
        if expiry is None:
            return True  # Not yet set; must register a watch
        now = datetime.now(tz=timezone.utc)
        return (expiry - now) < timedelta(hours=buffer_hours)
