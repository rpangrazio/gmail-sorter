"""Gmail watch registration and renewal helpers."""

from __future__ import annotations

import logging
import threading
from typing import Any

from gmail_sorter.config.models import PubSubConfig
from gmail_sorter.gmail.client import GmailClient

LOGGER = logging.getLogger(__name__)
_RENEWAL_INTERVAL_SECONDS = 6 * 24 * 60 * 60


class GmailWatcher:
    """Register and periodically renew Gmail watch subscriptions."""

    def __init__(self, gmail_client: GmailClient, config: PubSubConfig) -> None:
        """Store dependencies required to manage watch renewal."""

        self._gmail_client = gmail_client
        self._config = config
        self._timer: threading.Timer | None = None

    def register(self) -> dict[str, Any]:
        """Register Gmail watch notifications for the configured topic."""

        topic_name = f"projects/{self._config.project_id}/topics/{self._config.topic}"
        response = self._gmail_client.register_watch(topic_name)
        LOGGER.info("Registered Gmail watch for topic %s", topic_name)
        return response

    def schedule_renewal(self) -> None:
        """Schedule periodic watch renewal before Gmail watch expiry."""

        self._timer = threading.Timer(_RENEWAL_INTERVAL_SECONDS, self._renew_and_reschedule)
        self._timer.daemon = True
        self._timer.start()

    def stop(self) -> None:
        """Cancel a pending renewal timer if one is active."""

        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _renew_and_reschedule(self) -> None:
        """Renew Gmail watch and re-arm the timer."""

        try:
            self.register()
        except Exception:  # pragma: no cover - safety net logging branch
            LOGGER.exception("Failed to renew Gmail watch registration")
        finally:
            self.schedule_renewal()
