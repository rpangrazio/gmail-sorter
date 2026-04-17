"""Unit tests for Pub/Sub listener message handling."""

from __future__ import annotations

import json
import logging
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
        self.classification_errors_total = _FakeErrorMetric()


class _FakeErrorMetric:
    def __init__(self) -> None:
        self.by_error_type: dict[str, int] = {}

    def labels(self, error_type: str):
        return _FakeErrorMetricProxy(self.by_error_type, error_type)


class _FakeErrorMetricProxy:
    def __init__(self, store: dict[str, int], error_type: str) -> None:
        self._store = store
        self._error_type = error_type

    def inc(self) -> None:
        self._store[self._error_type] = self._store.get(self._error_type, 0) + 1


class _FakeSubscriberClient:
    def __init__(self, credentials=None) -> None:
        self.credentials = credentials
        self.subscription_path_value = "projects/project/subscriptions/subscription"
        self.last_subscription_request: dict | None = None

    def subscription_path(self, project_id: str, subscription: str) -> str:
        return f"projects/{project_id}/subscriptions/{subscription}"

    def subscribe(self, subscription_path: str, callback):
        _ = (subscription_path, callback)
        return SimpleNamespace(cancel=lambda: None)

    def create_subscription(self, request: dict) -> dict:
        self.last_subscription_request = request
        return request

    def close(self) -> None:
        return


class _FakePublisherClient:
    def __init__(self, credentials=None) -> None:
        self.credentials = credentials

    def topic_path(self, project_id: str, topic: str) -> str:
        return f"projects/{project_id}/topics/{topic}"

    def create_topic(self, name: str) -> dict:
        return {"name": name}

    def close(self) -> None:
        return


class _FakePushConfig:
    def __init__(self, push_endpoint: str) -> None:
        self.push_endpoint = push_endpoint


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


def _listener(config: PubSubConfig | None = None) -> PubSubListener:
    config = config or PubSubConfig(
        project_id="project",
        topic="topic",
        subscription="subscription",
        mode="pull",
    )

    return PubSubListener(config=config, engine=_FakeEngine(), metrics=_FakeMetrics())


@pytest.fixture(autouse=True)
def _stub_push_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gmail_sorter.pubsub.listener.pubsub_v1.types.PushConfig",
        _FakePushConfig,
    )


def _default_listener() -> PubSubListener:
    config = PubSubConfig(
        project_id="project",
        topic="topic",
        subscription="subscription",
        mode="pull",
    )
    return _listener(config)


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

    listener = _default_listener()
    monkeypatch.setattr(listener, "_get_message_ids_from_history", lambda _history_id: ["gmail-1"])
    monkeypatch.setattr(listener, "_run_classification", lambda _message_id: None)

    payload = json.dumps({"emailAddress": "user@example.com", "historyId": "123"}).encode("utf-8")
    message = _FakeMessage(payload)

    listener._handle_message(message)

    assert message.acked is True


def test_handle_message_does_not_ack_when_classification_fails(monkeypatch) -> None:
    """Listener should avoid ack on classification failures to allow redelivery."""

    listener = _default_listener()
    monkeypatch.setattr(listener, "_get_message_ids_from_history", lambda _history_id: ["gmail-1"])

    def _raise(_message_id: str) -> None:
        raise RuntimeError("classification failed")

    monkeypatch.setattr(listener, "_run_classification", _raise)

    payload = json.dumps({"emailAddress": "user@example.com", "historyId": "123"}).encode("utf-8")
    message = _FakeMessage(payload)

    listener._handle_message(message)

    assert message.acked is False
    assert listener._metrics.classification_errors_total.by_error_type["pubsub_error"] == 1


def test_handle_message_logs_pubsub_error_type(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    """Pub/Sub failures should use PRD error taxonomy labels in logs."""

    listener = _default_listener()
    monkeypatch.setattr(listener, "_get_message_ids_from_history", lambda _history_id: ["gmail-1"])

    def _raise(_message_id: str) -> None:
        raise RuntimeError("classification failed")

    monkeypatch.setattr(listener, "_run_classification", _raise)

    payload = json.dumps({"emailAddress": "user@example.com", "historyId": "123"}).encode("utf-8")
    message = _FakeMessage(payload, message_id="ps-9")

    with caplog.at_level(logging.ERROR):
        listener._handle_message(message)

    matching = [record for record in caplog.records if "Pub/Sub message processing failed" in record.getMessage()]
    assert matching
    assert getattr(matching[-1], "error_type", None) == "pubsub_error"


def test_get_message_ids_from_history_collects_all_pages() -> None:
    """History pagination should collect message IDs from each page."""

    listener = _default_listener()

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


def test_handle_message_logs_skip_outcome(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    """Listener should emit explicit skip outcomes with both message IDs."""

    listener = _default_listener()
    monkeypatch.setattr(listener, "_get_message_ids_from_history", lambda _history_id: ["gmail-1"])
    monkeypatch.setattr(
        listener,
        "_run_classification",
        lambda _message_id: SimpleNamespace(skipped=True),
    )

    payload = json.dumps({"emailAddress": "user@example.com", "historyId": "123"}).encode("utf-8")
    message = _FakeMessage(payload, message_id="ps-123")

    with caplog.at_level(logging.INFO):
        listener._handle_message(message)

    assert message.acked is True
    matching = [
        record
        for record in caplog.records
        if "Pub/Sub message processing outcome" in record.getMessage()
    ]
    assert matching
    context = getattr(matching[-1], "context", {})
    assert context.get("pubsub_message_id") == "ps-123"
    assert context.get("gmail_message_id") == "gmail-1"
    assert context.get("outcome") == "skip"


def test_push_mode_wires_configured_endpoint_and_port() -> None:
    """Push mode should use configured endpoint for subscription and routing."""

    config = PubSubConfig(
        project_id="project",
        topic="topic",
        subscription="subscription",
        mode="push",
        push_endpoint="http://localhost:8877/custom-pubsub",
        push_port=8877,
    )
    listener = _listener(config)

    listener._ensure_topic_and_subscription()

    subscription_request = listener._subscriber.last_subscription_request
    assert subscription_request is not None
    push_config = subscription_request.get("push_config")
    assert push_config is not None
    assert getattr(push_config, "push_endpoint", "") == "http://localhost:8877/custom-pubsub"
    assert listener._push_path() == "/custom-pubsub"


def test_listener_uses_default_pubsub_credentials_when_not_configured() -> None:
    """Default auth mode should construct clients without explicit credentials."""

    listener = _default_listener()
    assert listener._credentials is None
    assert listener._subscriber.credentials is None
    assert listener._publisher.credentials is None


def test_listener_loads_service_account_credentials(monkeypatch) -> None:
    """Service-account mode should load explicit credentials for Pub/Sub clients."""

    loaded = object()
    monkeypatch.setattr("gmail_sorter.pubsub.listener.Path.exists", lambda _self: True)
    monkeypatch.setattr(
        "gmail_sorter.pubsub.listener.service_account.Credentials.from_service_account_file",
        lambda _path: loaded,
    )

    config = PubSubConfig(
        project_id="project",
        topic="topic",
        subscription="subscription",
        mode="pull",
        auth_mode="service_account",
        credentials_path="/tmp/service-account.json",
    )
    listener = _listener(config)

    assert listener._credentials is loaded
    assert listener._subscriber.credentials is loaded
    assert listener._publisher.credentials is loaded


def test_listener_service_account_missing_file_raises_value_error(monkeypatch) -> None:
    """Service-account mode should fail fast when credentials file is missing."""

    monkeypatch.setattr("gmail_sorter.pubsub.listener.Path.exists", lambda _self: False)

    config = PubSubConfig(
        project_id="project",
        topic="topic",
        subscription="subscription",
        mode="pull",
        auth_mode="service_account",
        credentials_path="/tmp/missing-service-account.json",
    )

    with pytest.raises(ValueError, match="credentials file not found"):
        _listener(config)
