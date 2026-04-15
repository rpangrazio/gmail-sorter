"""Security-focused helper functions."""

from __future__ import annotations

import re

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
