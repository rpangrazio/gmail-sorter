"""Structured JSON logging configuration for the application."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Serialize log records into structured JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON-encoded representation of a log record."""

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "message": record.getMessage(),
            "error_type": getattr(record, "error_type", None),
            "context": self._context_from_record(record),
        }

        if payload["error_type"] is not None:
            payload["error_type"] = str(payload["error_type"])

        if record.exc_info:
            payload["context"].setdefault("exception", self.formatException(record.exc_info))

        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    def _context_from_record(record: logging.LogRecord) -> dict[str, Any]:
        """Extract the structured context dictionary from ``extra`` payload."""

        context = getattr(record, "context", None)
        if isinstance(context, dict):
            return context
        return {}


def configure_logging(level: str, log_prompts: bool) -> None:
    """Configure root logging with structured JSON output."""

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level.upper())

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(handler)

    root_logger.propagate = False
    setattr(root_logger, "gmail_sorter_log_prompts", bool(log_prompts))
