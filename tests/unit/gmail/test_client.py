"""Unit tests for Gmail API client wrapper behavior."""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest

from gmail_sorter.gmail.client import GmailClient


class _RateLimitError(Exception):
    """Test helper exception representing HTTP 429 responses."""

    status_code = 429


def _build_service() -> tuple[Mock, Mock]:
    service = Mock()
    users = service.users.return_value
    return service, users


def test_ensure_label_exists_uses_existing_label(monkeypatch) -> None:
    """Existing labels should be reused without creating duplicates."""

    service, users = _build_service()

    list_execute = users.labels.return_value.list.return_value.execute
    list_execute.return_value = {"labels": [{"id": "LBL-1", "name": "AutoSort/Marketing"}]}

    monkeypatch.setattr("gmail_sorter.gmail.client.build", lambda *_args, **_kwargs: service)

    client = GmailClient(credentials=Mock())
    label_id = client.ensure_label_exists("AutoSort/Marketing")

    assert label_id == "LBL-1"
    assert users.labels.return_value.create.call_count == 0


def test_apply_label_dry_run_does_not_call_api(monkeypatch) -> None:
    """Dry-run mode should log intent and skip API modification call."""

    service, users = _build_service()
    monkeypatch.setattr("gmail_sorter.gmail.client.build", lambda *_args, **_kwargs: service)

    client = GmailClient(credentials=Mock(), dry_run=True)
    client.apply_label("msg-1", "LBL-1", archive=False)

    assert users.messages.return_value.modify.call_count == 0


def test_apply_label_archive_removes_inbox(monkeypatch) -> None:
    """Archive flag should remove INBOX while applying target label."""

    service, users = _build_service()
    modify_execute = users.messages.return_value.modify.return_value.execute
    modify_execute.return_value = {}

    monkeypatch.setattr("gmail_sorter.gmail.client.build", lambda *_args, **_kwargs: service)

    client = GmailClient(credentials=Mock(), dry_run=False)
    client.apply_label("msg-1", "LBL-1", archive=True)

    call_kwargs = users.messages.return_value.modify.call_args.kwargs
    assert call_kwargs["body"]["addLabelIds"] == ["LBL-1"]
    assert call_kwargs["body"]["removeLabelIds"] == ["INBOX"]


def test_get_message_logs_warning_on_rate_limit(monkeypatch, caplog) -> None:
    """Rate-limited Gmail calls should emit warning logs with operation context."""

    service, users = _build_service()
    execute = users.messages.return_value.get.return_value.execute
    execute.side_effect = [_RateLimitError("Too many requests"), {"id": "msg-1"}]

    monkeypatch.setattr("gmail_sorter.gmail.client.build", lambda *_args, **_kwargs: service)
    monkeypatch.setattr("gmail_sorter.utils.retry.time.sleep", lambda _delay: None)

    client = GmailClient(credentials=Mock(), dry_run=False)

    with caplog.at_level(logging.WARNING):
        message = client.get_message("msg-1")

    assert message["id"] == "msg-1"
    assert any(
        "Gmail API rate limit encountered" in record.getMessage()
        and "operation=get_message" in record.getMessage()
        for record in caplog.records
    )


def test_client_rejects_non_https_transport(monkeypatch) -> None:
    """Client should fail fast when Gmail API base URL is not HTTPS."""

    service, _users = _build_service()
    service._baseUrl = "http://gmail.googleapis.com/gmail/v1/"
    monkeypatch.setattr("gmail_sorter.gmail.client.build", lambda *_args, **_kwargs: service)

    with pytest.raises(ValueError, match="Insecure Gmail API transport"):
        GmailClient(credentials=Mock())
