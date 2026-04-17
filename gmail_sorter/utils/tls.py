"""TLS security helpers for outbound HTTP clients."""

from __future__ import annotations

import ssl

_MIN_TLS_VERSION = ssl.TLSVersion.TLSv1_2


def build_tls12_context(context: ssl.SSLContext | None = None) -> ssl.SSLContext:
    """Return an SSL context enforcing TLS 1.2+ for outbound connections."""

    tls_context = context or ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    minimum_version = getattr(tls_context, "minimum_version", None)

    if minimum_version is not None and minimum_version < _MIN_TLS_VERSION:
        raise ValueError("TLS context minimum_version must be TLS 1.2 or higher.")

    if getattr(tls_context, "minimum_version", None) is None or tls_context.minimum_version < _MIN_TLS_VERSION:
        tls_context.minimum_version = _MIN_TLS_VERSION

    return tls_context
