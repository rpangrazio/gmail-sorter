"""Unit tests for structured JSON logging configuration."""

from __future__ import annotations

import json
import logging

from gmail_sorter.observability.logging import configure_logging


def test_configure_logging_emits_json_with_required_keys(capfd) -> None:
    """Configured logging should emit required JSON fields."""

    configure_logging("INFO", log_prompts=False)

    logger = logging.getLogger("gmail_sorter.tests.observability.logging")
    logger.info(
        "structured message",
        extra={"error_type": "api_error", "context": {"message_id": "m1"}},
    )

    captured = capfd.readouterr()
    output_line = captured.err.strip().splitlines()[-1]
    payload = json.loads(output_line)

    assert payload["timestamp"]
    assert payload["level"] == "INFO"
    assert payload["message"] == "structured message"
    assert payload["error_type"] == "api_error"
    assert payload["context"] == {"message_id": "m1"}


def test_configure_logging_normalizes_unknown_error_type(capfd) -> None:
    """Unknown error labels should be normalized to PRD taxonomy."""

    configure_logging("INFO", log_prompts=False)

    logger = logging.getLogger("gmail_sorter.tests.observability.logging.normalize")
    logger.error(
        "invalid taxonomy",
        extra={"error_type": "database_error", "context": {"operation": "test"}},
    )

    captured = capfd.readouterr()
    payload = json.loads(captured.err.strip().splitlines()[-1])

    assert payload["error_type"] == "api_error"
    assert payload["context"] == {"operation": "test"}
