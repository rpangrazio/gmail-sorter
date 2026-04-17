"""TLS helpers for outbound HTTP clients."""

from __future__ import annotations

import ssl

MINIMUM_TLS_VERSION = ssl.TLSVersion.TLSv1_2


def ensure_tls12_context(context: ssl.SSLContext | None = None) -> ssl.SSLContext:
    """Return an SSL context enforcing TLS 1.2+ for outbound connections."""

    tls_context = context or ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    minimum_version = getattr(tls_context, "minimum_version", None)
    if minimum_version is None or minimum_version < MINIMUM_TLS_VERSION:
        raise ValueError("TLS context must enforce minimum_version >= TLSv1_2.")
    return tls_context
