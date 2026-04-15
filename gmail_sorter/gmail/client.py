"""Gmail API client wrapper for message and label operations."""

from __future__ import annotations

import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from gmail_sorter.utils.retry import with_retry

LOGGER = logging.getLogger(__name__)


class GmailClient:
    """Wrap Gmail REST API operations used by the classification pipeline."""

    def __init__(self, credentials: Credentials, dry_run: bool = False) -> None:
        """Initialize Gmail API service from OAuth credentials."""

        self._service = build("gmail", "v1", credentials=credentials)
        self._dry_run = dry_run

    @with_retry(max_retries=3)
    def get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        """Fetch a Gmail message by ID."""

        return (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format=format)
            .execute()
        )

    @with_retry(max_retries=3)
    def list_messages(
        self,
        page_token: str | None = None,
        batch_size: int = 50,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """List mailbox messages and return the next pagination token."""

        response = (
            self._service.users()
            .messages()
            .list(userId="me", pageToken=page_token, maxResults=batch_size)
            .execute()
        )
        return response.get("messages", []), response.get("nextPageToken")

    @with_retry(max_retries=3)
    def list_labels(self) -> list[dict[str, Any]]:
        """List all Gmail labels for the authenticated account."""

        response = self._service.users().labels().list(userId="me").execute()
        return response.get("labels", [])

    @with_retry(max_retries=3)
    def create_label(self, name: str) -> dict[str, Any]:
        """Create a Gmail label and return API response payload."""

        body = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        return self._service.users().labels().create(userId="me", body=body).execute()

    @with_retry(max_retries=3)
    def ensure_label_exists(self, name: str) -> str:
        """Ensure label exists and return its Gmail label ID."""

        for label in self.list_labels():
            if label.get("name") == name:
                return str(label["id"])

        created = self.create_label(name)
        return str(created["id"])

    @with_retry(max_retries=3)
    def apply_label(self, message_id: str, label_id: str, archive: bool = False) -> None:
        """Apply a label to a message and optionally remove the INBOX label."""

        if self._dry_run:
            LOGGER.info(
                "Dry-run label apply: message_id=%s add_label=%s archive=%s",
                message_id,
                label_id,
                archive,
            )
            return

        body: dict[str, list[str]] = {"addLabelIds": [label_id]}
        if archive:
            body["removeLabelIds"] = ["INBOX"]

        (
            self._service.users()
            .messages()
            .modify(userId="me", id=message_id, body=body)
            .execute()
        )

    @with_retry(max_retries=3)
    def get_message_label_ids(self, message_id: str) -> list[str]:
        """Return applied label IDs for a message."""

        response = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="metadata")
            .execute()
        )
        return response.get("labelIds", [])

    @with_retry(max_retries=3)
    def register_watch(self, topic_name: str) -> dict[str, Any]:
        """Register Gmail watch notifications for INBOX updates."""

        body = {
            "topicName": topic_name,
            "labelIds": ["INBOX"],
            "labelFilterAction": "include",
        }
        return self._service.users().watch(userId="me", body=body).execute()

    @with_retry(max_retries=3)
    def list_history(
        self,
        start_history_id: str,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List Gmail history changes beginning at ``start_history_id``."""

        request: dict[str, Any] = {
            "userId": "me",
            "startHistoryId": start_history_id,
            "historyTypes": ["messageAdded"],
        }
        if page_token is not None:
            request["pageToken"] = page_token

        return self._service.users().history().list(**request).execute()
