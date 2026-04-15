"""Load test validating backfill throughput target."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest

from gmail_sorter.backfill.engine import BackfillEngine
from gmail_sorter.config.models import ProcessingConfig
from gmail_sorter.db.repository import Database


@dataclass(slots=True)
class _Result:
    skipped: bool


class _FakeGmailClient:
    """Provide deterministic paginated message IDs for backfill."""

    def __init__(self, total_messages: int, page_size: int = 100) -> None:
        self._pages: dict[str | None, tuple[list[dict[str, str]], str | None]] = {}
        generated = 0
        page_index = 0
        token: str | None = None

        while generated < total_messages:
            current_page_size = min(page_size, total_messages - generated)
            messages = [
                {"id": f"msg-{generated + offset + 1}"}
                for offset in range(current_page_size)
            ]
            generated += current_page_size
            next_token = None if generated >= total_messages else f"p{page_index + 1}"
            self._pages[token] = (messages, next_token)
            token = next_token
            page_index += 1

    def list_messages(
        self,
        page_token: str | None = None,
        batch_size: int = 50,
    ) -> tuple[list[dict[str, str]], str | None]:
        _ = batch_size
        return self._pages.get(page_token, ([], None))


class _FakeEngine:
    """Classifier stub with fixed latency per message."""

    def __init__(self, delay_seconds: float = 0.05) -> None:
        self._delay_seconds = delay_seconds

    async def classify_message(self, _message_id: str) -> _Result:
        await asyncio.sleep(self._delay_seconds)
        return _Result(skipped=False)


class _FakeMetrics:
    """Placeholder metrics collector for backfill engine tests."""


@pytest.mark.asyncio
async def test_backfill_throughput_is_at_least_500_messages_per_minute() -> None:
    """Backfill should satisfy NFR-002 throughput under default concurrency."""

    total_messages = 1000
    database = Database(":memory:")
    database.initialize()
    try:
        backfill = BackfillEngine(
            gmail_client=_FakeGmailClient(total_messages=total_messages, page_size=100),
            engine=_FakeEngine(delay_seconds=0.05),
            db=database,
            config=ProcessingConfig(
                body_max_length=4096,
                batch_size=100,
                backfill_concurrency=5,
                archive_after_label=False,
                dry_run=False,
            ),
            metrics=_FakeMetrics(),
        )

        started = time.perf_counter()
        await backfill.run()
        elapsed_seconds = time.perf_counter() - started
    finally:
        database.close()

    throughput_per_minute = total_messages / (elapsed_seconds / 60)
    assert throughput_per_minute >= 500
