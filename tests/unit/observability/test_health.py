"""Unit tests for health check endpoint behavior."""

from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from gmail_sorter.observability.health import HealthServer


def _read_health(port: int) -> tuple[int, dict[str, object]]:
    with urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
        status_code = response.getcode()
        payload = json.loads(response.read().decode("utf-8"))
    return status_code, payload


def test_health_server_returns_200_when_healthy(unused_tcp_port: int) -> None:
    """Healthy state should return HTTP 200 response."""

    server = HealthServer(port=unused_tcp_port)
    server.start()
    try:
        server.set_healthy(last_message_at="2026-04-15T00:00:00Z")
        status_code, payload = _read_health(unused_tcp_port)
    finally:
        server.stop()

    assert status_code == 200
    assert payload["status"] == "healthy"
    assert payload["pubsub_connected"] is True
    assert payload["last_message_at"] == "2026-04-15T00:00:00Z"


def test_health_server_returns_503_when_unhealthy(unused_tcp_port: int) -> None:
    """Unhealthy state should return HTTP 503 response."""

    server = HealthServer(port=unused_tcp_port)
    server.start()
    try:
        server.set_unhealthy("pubsub disconnected")
        with pytest.raises(HTTPError) as exc_info:
            _read_health(unused_tcp_port)
    finally:
        server.stop()

    assert exc_info.value.code == 503
    payload = json.loads(exc_info.value.read().decode("utf-8"))
    assert payload["status"] == "unhealthy"
    assert payload["reason"] == "pubsub disconnected"
