"""Idempotency checks for classification pipeline inputs."""

from __future__ import annotations

from gmail_sorter.db.repository import Database
from gmail_sorter.processor.email_parser import ProcessedEmail


class IdempotencyChecker:
    """Determine whether an email has already been processed."""

    def __init__(self, db: Database, system_label_ids: set[str]) -> None:
        """Initialize checker with database and managed label IDs."""

        self._db = db
        self._system_label_ids = system_label_ids

    def is_processed(self, email: ProcessedEmail) -> bool:
        """Return ``True`` when a message should be skipped as already handled."""

        if self._db.is_classified(email.message_id):
            return True

        return any(label_id in self._system_label_ids for label_id in email.raw_label_ids)
