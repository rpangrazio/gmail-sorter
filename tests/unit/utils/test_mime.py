"""Unit tests for MIME parsing and sanitization utilities."""

from __future__ import annotations

import base64

from gmail_sorter.utils.mime import EmailParser


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8")


def test_extract_body_prefers_plain_text_part() -> None:
    """Plain text MIME parts should be preferred over HTML."""

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>HTML body</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("Plain body")}},
        ],
    }

    assert EmailParser.extract_body(payload) == "Plain body"


def test_extract_body_falls_back_to_html_conversion() -> None:
    """HTML-only payloads should be converted to text."""

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"data": _b64("<html><body>Hello <b>world</b></body></html>")},
            }
        ],
    }

    body = EmailParser.extract_body(payload)
    assert "Hello" in body
    assert "world" in body


def test_extract_body_applies_truncation() -> None:
    """Extracted message body should be truncated to max_length."""

    payload = {
        "mimeType": "text/plain",
        "body": {"data": _b64("abcdefghijklmnopqrstuvwxyz")},
    }

    assert EmailParser.extract_body(payload, max_length=10) == "abcdefghij"


def test_strip_unsafe_content_removes_base64_data_uris() -> None:
    """Embedded base64 data URIs should be removed from text."""

    text = "before data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA after"
    sanitized = EmailParser.strip_unsafe_content(text)
    assert "data:image/png;base64" not in sanitized
    assert "before" in sanitized
    assert "after" in sanitized


def test_extract_body_html_fallback_strips_linked_images() -> None:
    """HTML fallback text should not include linked-image URLs."""

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {
                    "data": _b64(
                        "<html><body>"
                        "Hello"
                        "<img src='https://cdn.example.com/banner.png'/>"
                        " world"
                        "</body></html>"
                    )
                },
            }
        ],
    }

    body = EmailParser.extract_body(payload)
    assert "Hello" in body
    assert "world" in body
    assert "banner.png" not in body


def test_extract_body_html_fallback_strips_tracking_pixel_urls() -> None:
    """HTML fallback text should remove tracking/pixel links."""

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {
                    "data": _b64(
                        "<html><body>"
                        "Open details at "
                        "https://mail.example.com/pixel/open?id=12345 "
                        "for your account"
                        "</body></html>"
                    )
                },
            }
        ],
    }

    body = EmailParser.extract_body(payload)
    assert "for your account" in body
    assert "pixel/open" not in body
