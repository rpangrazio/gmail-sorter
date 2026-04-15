"""Raw Gmail message parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gmail_sorter.config.models import ProcessingConfig
from gmail_sorter.utils.mime import EmailParser


@dataclass(slots=True)
class ProcessedEmail:
    """Normalized email payload used by prompt construction and classification."""

    message_id: str
    thread_id: str
    sender: str
    subject: str
    date: str
    body: str
    headers: dict[str, str]
    raw_label_ids: list[str]


def process_message(raw: dict[str, Any], config: ProcessingConfig) -> ProcessedEmail:
    """Convert a raw Gmail API message into a ``ProcessedEmail``.

    Args:
        raw: Full Gmail API message payload.
        config: Processing configuration controlling body truncation.

    Returns:
        A normalized ``ProcessedEmail`` suitable for prompt rendering.
    """

    payload = raw.get("payload", {})
    extracted_headers = EmailParser.extract_headers(payload)

    body = EmailParser.extract_body(payload, max_length=config.body_max_length)
    body = EmailParser.strip_unsafe_content(body)
    body = body[: config.body_max_length]

    processed_headers = {
        "list_unsubscribe": extracted_headers.get("list_unsubscribe", "false"),
        "reply_to": extracted_headers.get("reply_to", ""),
    }

    return ProcessedEmail(
        message_id=str(raw.get("id", "")),
        thread_id=str(raw.get("threadId", "")),
        sender=extracted_headers.get("from", ""),
        subject=extracted_headers.get("subject", ""),
        date=extracted_headers.get("date", ""),
        body=body,
        headers=processed_headers,
        raw_label_ids=[str(label) for label in raw.get("labelIds", [])],
    )
