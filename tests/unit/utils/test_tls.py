"""Unit tests for TLS security helpers."""

from __future__ import annotations

import ssl

import pytest

from gmail_sorter.utils.tls import build_tls12_context


def test_build_tls12_context_sets_default_minimum_version() -> None:
    """Default helper context should enforce TLS 1.2+."""

    context = build_tls12_context()

    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_build_tls12_context_rejects_insecure_context() -> None:
    """Caller-provided contexts below TLS 1.2 should be rejected."""

    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1

    with pytest.raises(ValueError, match="TLS 1.2"):
        build_tls12_context(context)
