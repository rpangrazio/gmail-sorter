"""Unit tests for Gmail watcher registration scheduling."""

from __future__ import annotations

import logging

from gmail_sorter.config.models import PubSubConfig
from gmail_sorter.pubsub.watcher import GmailWatcher


class _FakeGmailClient:
    def __init__(self) -> None:
        self.topic_names: list[str] = []

    def register_watch(self, topic_name: str) -> dict:
        self.topic_names.append(topic_name)
        return {"historyId": "123"}


class _FakeTimer:
    def __init__(self, interval: float, callback) -> None:
        self.interval = interval
        self.callback = callback
        self.daemon = False
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True


def _watcher(client: _FakeGmailClient) -> GmailWatcher:
    config = PubSubConfig(
        project_id="project",
        topic="gmail-topic",
        subscription="sub",
        mode="pull",
    )
    return GmailWatcher(gmail_client=client, config=config)


def test_register_builds_project_topic_path() -> None:
    """Register should call Gmail watch with full topic path."""

    client = _FakeGmailClient()
    watcher = _watcher(client)

    watcher.register()

    assert client.topic_names == ["projects/project/topics/gmail-topic"]


def test_register_logs_structured_context(caplog) -> None:
    """Watch registration logs should include required structured context."""

    client = _FakeGmailClient()
    watcher = _watcher(client)

    with caplog.at_level(logging.INFO):
        watcher.register()

    matching = [record for record in caplog.records if "Registered Gmail watch" in record.getMessage()]
    assert matching
    context = getattr(matching[-1], "context", {})
    assert context.get("operation") == "watch_register"
    assert context.get("topic") == "projects/project/topics/gmail-topic"


def test_schedule_renewal_sets_timer_before_seven_days(monkeypatch) -> None:
    """Renewal timer should be configured at six days."""

    client = _FakeGmailClient()
    watcher = _watcher(client)
    captured_timer: dict[str, _FakeTimer] = {}

    def _timer_factory(interval: float, callback):
        timer = _FakeTimer(interval=interval, callback=callback)
        captured_timer["timer"] = timer
        return timer

    monkeypatch.setattr("gmail_sorter.pubsub.watcher.threading.Timer", _timer_factory)

    watcher.schedule_renewal()

    timer = captured_timer["timer"]
    assert timer.started is True
    assert timer.interval < 7 * 24 * 60 * 60


def test_stop_cancels_scheduled_timer(monkeypatch) -> None:
    """Stop should cancel the active renewal timer."""

    client = _FakeGmailClient()
    watcher = _watcher(client)
    captured_timer: dict[str, _FakeTimer] = {}

    def _timer_factory(interval: float, callback):
        timer = _FakeTimer(interval=interval, callback=callback)
        captured_timer["timer"] = timer
        return timer

    monkeypatch.setattr("gmail_sorter.pubsub.watcher.threading.Timer", _timer_factory)

    watcher.schedule_renewal()
    watcher.stop()

    assert captured_timer["timer"].cancelled is True
