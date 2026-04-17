"""Security-focused helper functions."""

from __future__ import annotations

import re
import ssl

_EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,}))")


def _extract_domain(sender: str) -> str | None:
    """Extract sender domain from either raw or display-name email format."""

    match = _EMAIL_PATTERN.search(sender)
    if not match:
        return None
    return match.group(2).lower()


def is_domain_allowed(sender: str, allowlist: list[str], blocklist: list[str]) -> bool:
    """Determine if sender domain passes allowlist and blocklist checks."""

    domain = _extract_domain(sender)
    if domain is None:
        return False

    normalized_blocklist = {item.lower() for item in blocklist}
    if domain in normalized_blocklist:
        return False

    if not allowlist:
        return True

    normalized_allowlist = {item.lower() for item in allowlist}
    return domain in normalized_allowlist


def create_tls12_context() -> ssl.SSLContext:
    """Create a TLS client context that enforces TLS 1.2 or newer."""

    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def ensure_tls12_minimum(context: ssl.SSLContext) -> ssl.SSLContext:
    """Validate that a TLS context rejects protocol versions older than 1.2."""

    minimum = context.minimum_version
    if minimum in {None, ssl.TLSVersion.MINIMUM_SUPPORTED} or minimum < ssl.TLSVersion.TLSv1_2:
        raise ValueError("TLS context must enforce TLS 1.2 or higher.")
    return context
