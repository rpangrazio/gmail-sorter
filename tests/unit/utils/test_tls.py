"""Unit tests for TLS enforcement helpers."""

from __future__ import annotations

import ssl
from types import SimpleNamespace

import pytest

from gmail_sorter.utils.tls import ensure_tls12_context


def test_ensure_tls12_context_accepts_tls12_or_higher() -> None:
    """Helper should accept contexts already enforcing TLS 1.2+."""

    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    result = ensure_tls12_context(context)

    assert result is context


def test_ensure_tls12_context_rejects_insecure_minimum_version() -> None:
    """Helper should reject contexts with minimum TLS below 1.2."""

    insecure_context = SimpleNamespace(minimum_version=ssl.TLSVersion.TLSv1)

    with pytest.raises(ValueError, match="TLS context must enforce"):
        ensure_tls12_context(insecure_context)  # type: ignore[arg-type]
