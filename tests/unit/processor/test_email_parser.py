"""Unit tests for processor-level Gmail message parsing."""

from __future__ import annotations

import base64

from gmail_sorter.config.models import ProcessingConfig
from gmail_sorter.processor.email_parser import process_message


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8")


def _processing_config(body_max_length: int = 4096) -> ProcessingConfig:
    return ProcessingConfig(
        body_max_length=body_max_length,
        batch_size=50,
        backfill_concurrency=5,
        archive_after_label=False,
        dry_run=False,
    )


def test_process_message_prefers_plain_text_multipart() -> None:
    """Plain text parts should be chosen when multipart alternatives exist."""

    raw_message = {
        "id": "msg-1",
        "threadId": "thread-1",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "Subject", "value": "Subject A"},
                {"name": "Date", "value": "Mon, 01 Jan 2026 00:00:00 +0000"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/html", "body": {"data": _b64("<p>HTML</p>")}},
                {"mimeType": "text/plain", "body": {"data": _b64("Plain text body")}},
            ],
        },
    }

    processed = process_message(raw_message, _processing_config())

    assert processed.message_id == "msg-1"
    assert processed.thread_id == "thread-1"
    assert processed.sender == "Sender <sender@example.com>"
    assert processed.subject == "Subject A"
    assert processed.body == "Plain text body"
    assert processed.raw_label_ids == ["INBOX", "UNREAD"]


def test_process_message_falls_back_to_html_text() -> None:
    """HTML-only payloads should be converted to readable text."""

    raw_message = {
        "id": "msg-2",
        "threadId": "thread-2",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Subject B"},
                {"name": "Date", "value": "Tue, 02 Jan 2026 00:00:00 +0000"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": _b64("<html><body>Hello <b>world</b></body></html>")},
                }
            ],
        },
    }

    processed = process_message(raw_message, _processing_config())

    assert "Hello" in processed.body
    assert "world" in processed.body


def test_process_message_enforces_body_truncation() -> None:
    """Processed body should be truncated to configured maximum length."""

    raw_message = {
        "id": "msg-3",
        "threadId": "thread-3",
        "payload": {
            "headers": [],
            "mimeType": "text/plain",
            "body": {"data": _b64("abcdefghijklmnopqrstuvwxyz")},
        },
    }

    processed = process_message(raw_message, _processing_config(body_max_length=10))
    assert processed.body == "abcdefghij"


def test_process_message_extracts_selected_headers() -> None:
    """List-Unsubscribe and Reply-To should be preserved in processed headers."""

    raw_message = {
        "id": "msg-4",
        "threadId": "thread-4",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Header test"},
                {"name": "Date", "value": "Wed, 03 Jan 2026 00:00:00 +0000"},
                {"name": "Reply-To", "value": "reply@example.com"},
                {"name": "List-Unsubscribe", "value": "<mailto:unsubscribe@example.com>"},
            ],
            "mimeType": "text/plain",
            "body": {"data": _b64("Body")},
        },
    }

    processed = process_message(raw_message, _processing_config())

    assert processed.headers["reply_to"] == "reply@example.com"
    assert processed.headers["list_unsubscribe"] == "true"
    assert processed.headers["to"] == "recipient@example.com"
