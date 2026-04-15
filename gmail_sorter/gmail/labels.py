"""Helpers for ensuring configured Gmail labels are present."""

from __future__ import annotations

from gmail_sorter.config.models import CategoryConfig
from gmail_sorter.gmail.client import GmailClient


class LabelManager:
    """Ensure all configured category labels exist in Gmail."""

    def __init__(self, client: GmailClient) -> None:
        """Store Gmail client used for label operations."""

        self._client = client

    def ensure_all_labels(self, categories: list[CategoryConfig]) -> dict[str, str]:
        """Create any missing labels and return category-to-label-id mapping."""

        mapping: dict[str, str] = {}
        for category in categories:
            mapping[category.name] = self._client.ensure_label_exists(category.label)
        return mapping
