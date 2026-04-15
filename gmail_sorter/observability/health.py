"""Minimal HTTP health endpoint server implementation."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


class HealthServer:
    """Run a lightweight ``/health`` endpoint in a daemon thread."""

    def __init__(self, port: int = 8080) -> None:
        """Initialize server state and health payload defaults."""

        self._port = port
        self._healthy = True
        self._last_message_at: str | None = None
        self._reason: str | None = None
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start serving the health endpoint if it is not running."""

        if self._server is not None:
            return

        parent = self

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/health":
                    self.send_response(404)
                    self.end_headers()
                    return

                with parent._lock:
                    healthy = parent._healthy
                    last_message_at = parent._last_message_at
                    reason = parent._reason

                if healthy:
                    status_code = 200
                    payload: dict[str, Any] = {
                        "status": "healthy",
                        "pubsub_connected": True,
                        "last_message_at": last_message_at,
                    }
                else:
                    status_code = 503
                    payload = {
                        "status": "unhealthy",
                        "reason": reason or "unknown",
                    }

                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

        self._server = HTTPServer(("0.0.0.0", self._port), HealthHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the health server and release server resources."""

        if self._server is None:
            return

        self._server.shutdown()
        self._server.server_close()
        self._server = None

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def set_healthy(self, last_message_at: str | None = None) -> None:
        """Set healthy state and optional last-message timestamp."""

        with self._lock:
            self._healthy = True
            self._reason = None
            self._last_message_at = last_message_at

    def set_unhealthy(self, reason: str) -> None:
        """Set unhealthy state with a diagnostic reason string."""

        with self._lock:
            self._healthy = False
            self._reason = reason
