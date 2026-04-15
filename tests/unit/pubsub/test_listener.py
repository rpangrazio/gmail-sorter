"""Unit tests for Pub/Sub listener message handling."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from gmail_sorter.config.models import PubSubConfig
from gmail_sorter.pubsub.listener import PubSubListener


class _FakeMetric:
    def __init__(self) -> None:
        self.count = 0

    def inc(self) -> None:
        self.count += 1


class _FakeMetrics:
    def __init__(self) -> None:
        self.pubsub_messages_received_total = _FakeMetric()


class _FakeSubscriberClient:
    def __init__(self) -> None:
        self.subscription_path_value = "projects/project/subscriptions/subscription"

    def subscription_path(self, project_id: str, subscription: str) -> str:
        return f"projects/{project_id}/subscriptions/{subscription}"

    def subscribe(self, subscription_path: str, callback):
        _ = (subscription_path, callback)
        return SimpleNamespace(cancel=lambda: None)

    def create_subscription(self, request: dict) -> dict:
        return request

    def close(self) -> None:
        return


class _FakePublisherClient:
    def topic_path(self, project_id: str, topic: str) -> str:
        return f"projects/{project_id}/topics/{topic}"

    def create_topic(self, name: str) -> dict:
        return {"name": name}

    def close(self) -> None:
        return


class _FakeGmailClient:
    def list_history(self, start_history_id: str, page_token: str | None = None) -> dict:
        _ = (start_history_id, page_token)
        return {"history": []}


class _FakeEngine:
    def __init__(self) -> None:
        self._gmail_client = _FakeGmailClient()

    async def classify_message(self, _message_id: str) -> None:
        return


class _FakeMessage:
    def __init__(self, data: bytes, message_id: str = "ps-1") -> None:
        self.data = data
        self.message_id = message_id
        self.acked = False

    def ack(self) -> None:
        self.acked = True


def _listener() -> PubSubListener:
    config = PubSubConfig(
        project_id="project",
        topic="topic",
        subscription="subscription",
        mode="pull",
    )
    return PubSubListener(config=config, engine=_FakeEngine(), metrics=_FakeMetrics())


@pytest.fixture(autouse=True)
def _stub_pubsub_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gmail_sorter.pubsub.listener.pubsub_v1.SubscriberClient",
        _FakeSubscriberClient,
    )
    monkeypatch.setattr(
        "gmail_sorter.pubsub.listener.pubsub_v1.PublisherClient",
        _FakePublisherClient,
    )


def test_handle_message_acknowledges_after_success(monkeypatch) -> None:
    """Listener should ack only after classification completes."""

    listener = _listener()
    monkeypatch.setattr(listener, "_get_message_ids_from_history", lambda _history_id: ["gmail-1"])
    monkeypatch.setattr(listener, "_run_classification", lambda _message_id: None)

    payload = json.dumps({"emailAddress": "user@example.com", "historyId": "123"}).encode("utf-8")
    message = _FakeMessage(payload)

    listener._handle_message(message)

    assert message.acked is True


def test_handle_message_does_not_ack_when_classification_fails(monkeypatch) -> None:
    """Listener should avoid ack on classification failures to allow redelivery."""

    listener = _listener()
    monkeypatch.setattr(listener, "_get_message_ids_from_history", lambda _history_id: ["gmail-1"])

    def _raise(_message_id: str) -> None:
        raise RuntimeError("classification failed")

    monkeypatch.setattr(listener, "_run_classification", _raise)

    payload = json.dumps({"emailAddress": "user@example.com", "historyId": "123"}).encode("utf-8")
    message = _FakeMessage(payload)

    listener._handle_message(message)

    assert message.acked is False


def test_get_message_ids_from_history_collects_all_pages() -> None:
    """History pagination should collect message IDs from each page."""

    listener = _listener()

    responses = [
        {
            "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}],
            "nextPageToken": "token-1",
        },
        {
            "history": [{"messagesAdded": [{"message": {"id": "m2"}}]}],
        },
    ]

    gmail_client = SimpleNamespace()
    gmail_client.list_history = lambda start_history_id, page_token=None: responses.pop(0)
    listener._engine = SimpleNamespace(_gmail_client=gmail_client)

    assert listener._get_message_ids_from_history("100") == ["m1", "m2"]
