"""Load test validating idle listener memory footprint."""

from __future__ import annotations

import asyncio
import tracemalloc

import pytest

from gmail_sorter.config.models import PubSubConfig
from gmail_sorter.pubsub.listener import PubSubListener


class _FakeCounter:
    def __init__(self) -> None:
        self.count = 0

    def inc(self) -> None:
        self.count += 1


class _FakeMetrics:
    def __init__(self) -> None:
        self.pubsub_messages_received_total = _FakeCounter()


class _FakeEngine:
    """Classifier placeholder; no messages are processed in this test."""

    async def classify_message(self, _message_id: str) -> None:
        return


@pytest.mark.asyncio
async def test_pubsub_listener_idle_memory_peak_under_256mb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Idle listener memory usage should satisfy NFR-007."""

    class _Subscriber:
        def subscription_path(self, project_id: str, subscription: str) -> str:
            return f"projects/{project_id}/subscriptions/{subscription}"

        def create_subscription(self, request: dict) -> None:
            _ = request

        def subscribe(self, _subscription_path: str, callback):
            _ = callback

            class _Future:
                def cancel(self) -> None:
                    return

            return _Future()

        def close(self) -> None:
            return

    class _Publisher:
        def topic_path(self, project_id: str, topic: str) -> str:
            return f"projects/{project_id}/topics/{topic}"

        def create_topic(self, name: str) -> None:
            _ = name

        def close(self) -> None:
            return

    monkeypatch.setattr(
        "gmail_sorter.pubsub.listener.pubsub_v1.SubscriberClient",
        lambda: _Subscriber(),
    )
    monkeypatch.setattr(
        "gmail_sorter.pubsub.listener.pubsub_v1.PublisherClient",
        lambda: _Publisher(),
    )

    listener = PubSubListener(
        config=PubSubConfig(
            project_id="project",
            topic="topic",
            subscription="subscription",
            mode="pull",
        ),
        engine=_FakeEngine(),
        metrics=_FakeMetrics(),
    )

    tracemalloc.start()
    try:
        task = asyncio.create_task(listener.start())
        await asyncio.sleep(5)
        await listener.stop()
        await task
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak_bytes < 256 * 1024 * 1024
