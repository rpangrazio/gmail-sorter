"""MIME parsing and sanitization helpers for Gmail message payloads."""

from __future__ import annotations

import base64
import re
from typing import Any

from bs4 import BeautifulSoup

_DATA_URI_PATTERN = re.compile(r"data:[^;]+;base64,[A-Za-z0-9+/=]+")
_IMAGE_URL_PATTERN = re.compile(
    r"https?://[^\s]+\.(?:png|jpe?g|gif|webp|bmp|svg)(?:\?[^\s]*)?",
    re.IGNORECASE,
)
_TRACKING_URL_PATTERN = re.compile(
    r"https?://[^\s]*(?:track|tracking|beacon|pixel|open)[^\s]*",
    re.IGNORECASE,
)


class EmailParser:
    """Utility methods for extracting safe text content from MIME payloads."""

    @staticmethod
    def extract_body(payload: dict[str, Any], max_length: int = 4096) -> str:
        """Extract a plain-text body from a Gmail message payload.

        Prefers ``text/plain`` parts. If none exist, uses ``text/html`` parts
        and converts them to plain text.
        """

        plain_part = EmailParser._find_part(payload, "text/plain")
        if plain_part is not None:
            text = EmailParser._decode_part_data(plain_part)
        else:
            html_part = EmailParser._find_part(payload, "text/html")
            if html_part is None:
                text = ""
            else:
                text = EmailParser.html_to_text(EmailParser._decode_part_data(html_part))

        return text[:max_length]

    @staticmethod
    def extract_headers(payload: dict[str, Any]) -> dict[str, str]:
        """Extract useful headers from a Gmail message payload."""

        headers = payload.get("headers", [])
        index: dict[str, str] = {
            str(item.get("name", "")).lower(): str(item.get("value", ""))
            for item in headers
        }
        return {
            "from": index.get("from", ""),
            "to": index.get("to", ""),
            "subject": index.get("subject", ""),
            "date": index.get("date", ""),
            "reply_to": index.get("reply-to", ""),
            "list_unsubscribe": "true" if "list-unsubscribe" in index else "false",
        }

    @staticmethod
    def html_to_text(html: str) -> str:
        """Convert HTML content to plain text."""

        soup = BeautifulSoup(html, "lxml")

        for tag_name in (
            "script",
            "style",
            "head",
            "title",
            "meta",
            "link",
            "img",
            "picture",
            "source",
            "svg",
            "canvas",
            "noscript",
        ):
            for tag in soup.find_all(tag_name):
                tag.decompose()

        text = soup.get_text(separator=" ")
        return EmailParser._strip_tracking_urls(text)

    @staticmethod
    def strip_unsafe_content(text: str) -> str:
        """Remove base64 data URIs from text content."""

        return _DATA_URI_PATTERN.sub("", text)

    @staticmethod
    def _strip_tracking_urls(text: str) -> str:
        """Remove linked-image and tracking-style URLs from extracted text."""

        without_image_urls = _IMAGE_URL_PATTERN.sub("", text)
        return _TRACKING_URL_PATTERN.sub("", without_image_urls)

    @staticmethod
    def _find_part(payload: dict[str, Any], mime_type: str) -> dict[str, Any] | None:
        """Recursively find the first MIME part matching ``mime_type``."""

        if payload.get("mimeType") == mime_type:
            return payload

        for part in payload.get("parts", []):
            found = EmailParser._find_part(part, mime_type)
            if found is not None:
                return found
        return None

    @staticmethod
    def _decode_part_data(part: dict[str, Any]) -> str:
        """Decode Gmail URL-safe base64 part body data to UTF-8 text."""

        data = str(part.get("body", {}).get("data", ""))
        if not data:
            return ""

        padded = data + "=" * (-len(data) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
        except (ValueError, TypeError):
            return ""
        return decoded.decode("utf-8", errors="replace")
