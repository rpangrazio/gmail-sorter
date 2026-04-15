"""Unit tests for security utility functions."""

from __future__ import annotations

from gmail_sorter.utils.security import is_domain_allowed


def test_blocklisted_domain_is_rejected() -> None:
    """Blocklisted domains should always be rejected."""

    assert (
        is_domain_allowed(
            sender="alerts@example.com",
            allowlist=[],
            blocklist=["example.com"],
        )
        is False
    )


def test_empty_allowlist_allows_non_blocklisted_domain() -> None:
    """Empty allowlist should permit any non-blocklisted domain."""

    assert (
        is_domain_allowed(
            sender="Name <person@allowed.com>",
            allowlist=[],
            blocklist=["blocked.com"],
        )
        is True
    )


def test_nonempty_allowlist_rejects_domain_not_present() -> None:
    """Domains outside a non-empty allowlist should be rejected."""

    assert (
        is_domain_allowed(
            sender="person@outside.com",
            allowlist=["allowed.com"],
            blocklist=[],
        )
        is False
    )


def test_nonempty_allowlist_accepts_matching_domain() -> None:
    """Domains present in allowlist should be accepted when not blocked."""

    assert (
        is_domain_allowed(
            sender="Person <person@allowed.com>",
            allowlist=["allowed.com"],
            blocklist=[],
        )
        is True
    )
