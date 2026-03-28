"""
Gmail API client wrapper.

Provides a high-level interface over the Gmail REST API, including:
- Retrieving the user profile and initial history cursor
- Registering / renewing Gmail watch notifications via Cloud Pub/Sub
- Fetching history records (new messages, label changes) since a cursor
- Fetching full message content
- Applying Gmail labels to messages

All methods include automatic exponential-backoff retry on transient
HTTP errors (429 Rate Limit, 5xx Server Error).
"""

import base64
import email as email_lib
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# System label IDs that indicate an email should NOT be sorted.
# INBOX: already in inbox — we want to sort these.
# SENT / DRAFT: outgoing; skip.
# SPAM / TRASH: skip.
_SKIP_LABEL_IDS = {"SENT", "DRAFT", "SPAM", "TRASH"}

# Maximum number of retries on transient API errors.
_MAX_RETRIES = 5
# Base delay (seconds) for exponential backoff.
_RETRY_BASE_DELAY = 1.0


class GmailClient:
    """
    High-level Gmail API client with retry handling.

    Args:
        service: An authenticated Gmail API service resource built via
            ``googleapiclient.discovery.build('gmail', 'v1', credentials=...)``.
        user_id: Gmail user identifier.  ``"me"`` refers to the authenticated user.
    """

    def __init__(self, service: Resource, user_id: str = "me") -> None:
        self._service = service
        self._user_id = user_id

    # ------------------------------------------------------------------
    # Profile and watch management
    # ------------------------------------------------------------------

    def get_profile(self) -> Dict[str, Any]:
        """
        Return the authenticated user's Gmail profile.

        Returns:
            Dict with keys ``emailAddress`` (str) and ``historyId`` (str).
        """
        return self._execute(
            self._service.users().getProfile(userId=self._user_id)
        )

    def ensure_watch(self, topic_name: str, state_manager) -> None:
        """
        Register (or renew) a Gmail watch on the user's inbox.

        Gmail watch registrations expire after 7 days.  This method
        renews the watch if it is absent or expiring within 24 hours.

        Args:
            topic_name: Full Pub/Sub topic resource name that Gmail should
                publish change notifications to
                (e.g., ``"projects/my-proj/topics/gmail-sorter"``).
            state_manager: :class:`~src.state_manager.StateManager` instance
                used to persist the watch expiry timestamp.
        """
        if not state_manager.is_watch_expiring_soon():
            logger.debug("Gmail watch is still valid; no renewal needed.")
            return

        logger.info("Registering Gmail watch on topic: %s", topic_name)
        response = self._execute(
            self._service.users().watch(
                userId=self._user_id,
                body={
                    "topicName": topic_name,
                    "labelIds": ["INBOX"],
                    "labelFilterBehavior": "INCLUDE",
                },
            )
        )
        expiry_ms = int(response["expiration"])
        state_manager.set_watch_expiry(expiry_ms)
        logger.info(
            "Gmail watch registered. History ID: %s, expires at epoch ms: %d",
            response.get("historyId"),
            expiry_ms,
        )

    # ------------------------------------------------------------------
    # History API
    # ------------------------------------------------------------------

    def list_new_messages(self, start_history_id: str) -> Tuple[List[str], str]:
        """
        Return message IDs of emails added to the inbox since *start_history_id*.

        Uses ``users.history.list`` and filters for ``messagesAdded`` events
        in the INBOX label, skipping SENT, DRAFT, SPAM, and TRASH messages.

        Args:
            start_history_id: The last processed history ID.  Only changes
                *after* this point are returned.

        Returns:
            A tuple of ``(message_ids, max_history_id)`` where:

            - ``message_ids``: List of Gmail message ID strings for new
              inbox messages.
            - ``max_history_id``: The highest history ID seen in this batch,
              suitable for use as the next ``start_history_id``.

        Raises:
            HistoryExpiredError: If Gmail returns HTTP 404 because the
                history ID is too old (> 30 days).
        """
        message_ids: List[str] = []
        max_history_id = start_history_id
        page_token: Optional[str] = None

        while True:
            kwargs: Dict[str, Any] = {
                "userId": self._user_id,
                "startHistoryId": start_history_id,
                "historyTypes": ["messageAdded"],
                "labelId": "INBOX",
                "maxResults": 500,
            }
            if page_token:
                kwargs["pageToken"] = page_token

            try:
                response = self._execute(
                    self._service.users().history().list(**kwargs)
                )
            except HttpError as exc:
                if exc.resp.status == 404:
                    raise HistoryExpiredError(
                        f"History ID {start_history_id!r} is too old. "
                        "The agent will reset to the current cursor."
                    ) from exc
                raise

            for record in response.get("history", []):
                record_history_id = record.get("id", start_history_id)
                if record_history_id > max_history_id:
                    max_history_id = record_history_id

                for added in record.get("messagesAdded", []):
                    msg = added.get("message", {})
                    label_ids = set(msg.get("labelIds", []))

                    # Skip outgoing or spam/trash messages.
                    if label_ids & _SKIP_LABEL_IDS:
                        continue
                    # Only process messages in the INBOX.
                    if "INBOX" not in label_ids:
                        continue

                    message_ids.append(msg["id"])

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        logger.debug(
            "History list: %d new messages since history ID %s",
            len(message_ids),
            start_history_id,
        )
        return message_ids, max_history_id

    # ------------------------------------------------------------------
    # Message fetching
    # ------------------------------------------------------------------

    def get_message(self, message_id: str) -> Dict[str, Any]:
        """
        Fetch a message and extract its displayable fields.

        Returns:
            Dict with keys:

            - ``id`` (str): Gmail message ID.
            - ``subject`` (str): Email subject line.
            - ``from_`` (str): Sender address.
            - ``to`` (str): Recipient(s).
            - ``date`` (str): Date header value.
            - ``snippet`` (str): Gmail's 200-character plain-text snippet.
            - ``body`` (str): Decoded plain-text body (up to 8,000 characters).
        """
        raw = self._execute(
            self._service.users()
            .messages()
            .get(userId=self._user_id, id=message_id, format="full")
        )

        headers = {
            h["name"].lower(): h["value"]
            for h in raw.get("payload", {}).get("headers", [])
        }

        body = _extract_body(raw.get("payload", {}))

        return {
            "id": raw["id"],
            "subject": headers.get("subject", "(no subject)"),
            "from_": headers.get("from", "(unknown sender)"),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "snippet": raw.get("snippet", ""),
            "body": body[:8_000],  # Limit body length for the classifier
        }

    # ------------------------------------------------------------------
    # Label application
    # ------------------------------------------------------------------

    def apply_label(self, message_id: str, label_id: str) -> None:
        """
        Add a label to a Gmail message.

        Args:
            message_id: The Gmail message ID to label.
            label_id: The Gmail label ID to apply.
        """
        self._execute(
            self._service.users()
            .messages()
            .modify(
                userId=self._user_id,
                id=message_id,
                body={"addLabelIds": [label_id]},
            )
        )
        logger.debug("Label %s applied to message %s.", label_id, message_id)

    # ------------------------------------------------------------------
    # Internal retry wrapper
    # ------------------------------------------------------------------

    def _execute(self, request) -> Any:
        """
        Execute a Gmail API request with exponential-backoff retry.

        Retries on HTTP 429 (rate limit) and 5xx (server error) responses.
        Raises immediately on client errors (4xx other than 429).

        Args:
            request: An un-executed ``googleapiclient`` request object.

        Returns:
            The API response dict.

        Raises:
            googleapiclient.errors.HttpError: After all retries are exhausted,
                or on non-retryable errors.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                return request.execute()
            except HttpError as exc:
                status = exc.resp.status
                if status == 429 or status >= 500:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Gmail API error %d (attempt %d/%d); retrying in %.1fs...",
                        status,
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    raise
        raise exc  # noqa: F821 — reached only when all retries are exhausted


class HistoryExpiredError(Exception):
    """Raised when the Gmail history cursor is too old to be used."""


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _extract_body(payload: Dict[str, Any], max_chars: int = 8_000) -> str:
    """
    Recursively extract the plain-text body from a Gmail message payload.

    Prefers ``text/plain`` parts; falls back to stripping HTML tags from
    ``text/html`` parts.

    Args:
        payload: The Gmail message ``payload`` dict (may be nested with parts).
        max_chars: Maximum number of characters to return.

    Returns:
        Decoded plain-text body string, or empty string if none found.
    """
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return _decode_base64url(body_data)[:max_chars]

    # Recurse into multipart/* parts.
    parts = payload.get("parts", [])
    # Prefer plain text over HTML.
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return _decode_base64url(data)[:max_chars]

    for part in parts:
        result = _extract_body(part, max_chars)
        if result:
            return result

    # If the top-level part is HTML, do a minimal tag strip.
    if mime_type == "text/html" and body_data:
        html = _decode_base64url(body_data)
        return _strip_html_tags(html)[:max_chars]

    return ""


def _decode_base64url(data: str) -> str:
    """Decode a Gmail base64url-encoded string to UTF-8 text."""
    try:
        padded = data + "=" * (4 - len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _strip_html_tags(html: str) -> str:
    """Minimal HTML tag remover (no external dependencies)."""
    import re
    # Remove script and style blocks.
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.I)
    # Replace block-level tags with newlines.
    html = re.sub(r"<(br|p|div|li|tr)[^>]*>", "\n", html, flags=re.I)
    # Strip remaining tags.
    html = re.sub(r"<[^>]+>", "", html)
    # Collapse whitespace.
    html = re.sub(r"\s{2,}", " ", html)
    return html.strip()
