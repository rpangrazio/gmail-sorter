"""Integration-style tests for Gmail client behavior."""

from __future__ import annotations

from unittest.mock import Mock

from gmail_sorter.gmail.client import GmailClient


def _build_service() -> tuple[Mock, Mock]:
    service = Mock()
    users = service.users.return_value
    return service, users


def test_ensure_label_exists_returns_existing_id(monkeypatch) -> None:
    """ensure_label_exists should reuse an existing Gmail label."""

    service, users = _build_service()
    users.labels.return_value.list.return_value.execute.return_value = {
        "labels": [{"id": "LBL-1", "name": "AutoSort/Alerts"}]
    }

    monkeypatch.setattr("gmail_sorter.gmail.client.build", lambda *_a, **_k: service)

    client = GmailClient(credentials=Mock())
    label_id = client.ensure_label_exists("AutoSort/Alerts")

    assert label_id == "LBL-1"
    assert users.labels.return_value.create.call_count == 0


def test_ensure_label_exists_creates_when_absent(monkeypatch) -> None:
    """ensure_label_exists should create labels that do not exist yet."""

    service, users = _build_service()
    users.labels.return_value.list.return_value.execute.return_value = {"labels": []}
    users.labels.return_value.create.return_value.execute.return_value = {
        "id": "LBL-NEW",
        "name": "AutoSort/New",
    }

    monkeypatch.setattr("gmail_sorter.gmail.client.build", lambda *_a, **_k: service)

    client = GmailClient(credentials=Mock())
    label_id = client.ensure_label_exists("AutoSort/New")

    assert label_id == "LBL-NEW"
    create_kwargs = users.labels.return_value.create.call_args.kwargs
    assert create_kwargs["body"]["name"] == "AutoSort/New"


def test_apply_label_retries_on_transient_rate_limit(monkeypatch) -> None:
    """apply_label should retry transient failures and eventually succeed."""

    service, users = _build_service()
    users.messages.return_value.modify.return_value.execute.side_effect = [
        RuntimeError("429 Too Many Requests"),
        {},
    ]

    monkeypatch.setattr("gmail_sorter.gmail.client.build", lambda *_a, **_k: service)

    client = GmailClient(credentials=Mock())
    client.apply_label("msg-1", "LBL-1", archive=True)

    assert users.messages.return_value.modify.return_value.execute.call_count == 2
    modify_kwargs = users.messages.return_value.modify.call_args.kwargs
    assert modify_kwargs["id"] == "msg-1"
    assert modify_kwargs["body"]["addLabelIds"] == ["LBL-1"]
    assert modify_kwargs["body"]["removeLabelIds"] == ["INBOX"]
