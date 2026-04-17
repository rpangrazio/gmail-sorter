"""Gmail API client wrapper for message and label operations."""

from __future__ import annotations

import logging
from urllib.parse import urlparse
from collections.abc import Callable
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gmail_sorter.utils.retry import with_retry

LOGGER = logging.getLogger(__name__)


class GmailClient:
    """Wrap Gmail REST API operations used by the classification pipeline."""

    def __init__(self, credentials: Credentials, dry_run: bool = False) -> None:
        """Initialize Gmail API service from OAuth credentials."""

        self._service = build("gmail", "v1", credentials=credentials)
        self._validate_secure_transport()
        self._dry_run = dry_run

    def _validate_secure_transport(self) -> None:
        """Enforce TLS transport policy for Gmail API HTTP communications."""

        base_url = str(getattr(self._service, "_baseUrl", ""))
        if not base_url:
            return

        parsed = urlparse(base_url)
        if parsed.scheme and parsed.scheme.lower() != "https":
            raise ValueError(
                "Insecure Gmail API transport detected: expected https endpoint "
                f"but got {base_url!r}."
            )

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status == 429:
            return True

        if isinstance(exc, HttpError):
            if getattr(exc.resp, "status", None) == 429:
                return True

            reason_text = ""
            try:
                reason_text = exc._get_reason().lower()
            except Exception:  # pragma: no cover - defensive fallback
                reason_text = ""

            content = getattr(exc, "content", b"")
            if isinstance(content, bytes):
                content_text = content.decode("utf-8", errors="ignore").lower()
            else:
                content_text = str(content).lower()

            combined_text = f"{reason_text} {content_text}"
            return (
                "too many requests" in combined_text
                or "ratelimit" in combined_text
                or "rate limit" in combined_text
                or "userratelimitexceeded" in combined_text
            )

        return False

    def _execute_with_rate_limit_warning(
        self,
        operation: str,
        execute_call: Callable[[], Any],
    ) -> Any:
        try:
            return execute_call()
        except Exception as exc:
            if self._is_rate_limit_error(exc):
                LOGGER.warning(
                    "Gmail API rate limit encountered; retrying operation=%s error=%s",
                    operation,
                    exc,
                )
            raise

    @with_retry(max_retries=3)
    def get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        """Fetch a Gmail message by ID."""

        request = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format=format)
        )
        return self._execute_with_rate_limit_warning("get_message", request.execute)

    @with_retry(max_retries=3)
    def list_messages(
        self,
        page_token: str | None = None,
        batch_size: int = 50,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """List mailbox messages and return the next pagination token."""

        request = (
            self._service.users()
            .messages()
            .list(userId="me", pageToken=page_token, maxResults=batch_size)
        )
        response = self._execute_with_rate_limit_warning("list_messages", request.execute)
        return response.get("messages", []), response.get("nextPageToken")

    @with_retry(max_retries=3)
    def list_labels(self) -> list[dict[str, Any]]:
        """List all Gmail labels for the authenticated account."""

        request = self._service.users().labels().list(userId="me")
        response = self._execute_with_rate_limit_warning("list_labels", request.execute)
        return response.get("labels", [])

    @with_retry(max_retries=3)
    def create_label(self, name: str) -> dict[str, Any]:
        """Create a Gmail label and return API response payload."""

        body = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        request = self._service.users().labels().create(userId="me", body=body)
        return self._execute_with_rate_limit_warning("create_label", request.execute)

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

        request = (
            self._service.users()
            .messages()
            .modify(userId="me", id=message_id, body=body)
        )
        self._execute_with_rate_limit_warning("apply_label", request.execute)

    @with_retry(max_retries=3)
    def get_message_label_ids(self, message_id: str) -> list[str]:
        """Return applied label IDs for a message."""

        request = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="metadata")
        )
        response = self._execute_with_rate_limit_warning(
            "get_message_label_ids",
            request.execute,
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
        request = self._service.users().watch(userId="me", body=body)
        return self._execute_with_rate_limit_warning("register_watch", request.execute)

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

        history_request = self._service.users().history().list(**request)
        return self._execute_with_rate_limit_warning(
            "list_history",
            history_request.execute,
        )
