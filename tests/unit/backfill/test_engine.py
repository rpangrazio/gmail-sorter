"""Unit tests for backfill engine orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from gmail_sorter.backfill.engine import BackfillEngine
from gmail_sorter.config.models import ProcessingConfig
from gmail_sorter.db.repository import BackfillState


@dataclass(slots=True)
class _Result:
    skipped: bool


class _FakeGmailClient:
    def __init__(self, pages: dict[str | None, tuple[list[dict[str, str]], str | None]]) -> None:
        self._pages = pages
        self.calls: list[tuple[str | None, int]] = []

    def list_messages(
        self,
        page_token: str | None = None,
        batch_size: int = 50,
    ) -> tuple[list[dict[str, str]], str | None]:
        self.calls.append((page_token, batch_size))
        return self._pages.get(page_token, ([], None))


class _FakeDatabase:
    def __init__(self, initial_state: BackfillState | None = None) -> None:
        self._state = initial_state
        self.saved_states: list[BackfillState] = []
        self._next_id = 1 if initial_state is None else (initial_state.id or 1) + 1

    def get_latest_backfill_state(self) -> BackfillState | None:
        return self._state

    def upsert_backfill_state(self, state: BackfillState) -> None:
        if state.id is None:
            state.id = self._next_id
            self._next_id += 1
        snapshot = BackfillState(
            id=state.id,
            last_page_token=state.last_page_token,
            last_message_id=state.last_message_id,
            status=state.status,
            started_at=state.started_at,
            completed_at=state.completed_at,
            total_processed=state.total_processed,
            total_skipped=state.total_skipped,
        )
        self._state = snapshot
        self.saved_states.append(snapshot)


class _FakeMetrics:
    pass


def _processing_config(concurrency: int = 2, progress_interval: int = 100) -> ProcessingConfig:
    return ProcessingConfig(
        body_max_length=4096,
        batch_size=2,
        backfill_concurrency=concurrency,
        archive_after_label=False,
        dry_run=False,
        backfill_progress_interval=progress_interval,
    )


@pytest.mark.asyncio
async def test_run_processes_all_paginated_message_ids() -> None:
    pages = {
        None: ([{"id": "m1"}, {"id": "m2"}], "p2"),
        "p2": ([{"id": "m3"}, {"id": "m4"}], "p3"),
        "p3": ([{"id": "m5"}], None),
    }
    gmail_client = _FakeGmailClient(pages)
    processed_ids: list[str] = []

    class _Engine:
        async def classify_message(self, message_id: str) -> _Result:
            processed_ids.append(message_id)
            return _Result(skipped=False)

    db = _FakeDatabase()
    backfill = BackfillEngine(
        gmail_client=gmail_client,
        engine=_Engine(),
        db=db,
        config=_processing_config(concurrency=3),
        metrics=_FakeMetrics(),
    )

    await backfill.run()

    assert processed_ids == ["m1", "m2", "m3", "m4", "m5"]
    assert db.saved_states[-1].status == "completed"
    assert db.saved_states[-1].total_processed == 5
    assert db.saved_states[-1].last_page_token is None


@pytest.mark.asyncio
async def test_run_resumes_from_interrupted_state_page_token() -> None:
    interrupted = BackfillState(
        id=7,
        last_page_token="resume-token",
        last_message_id="m-prev",
        status="interrupted",
        started_at="2026-04-15T00:00:00Z",
        completed_at="2026-04-15T00:01:00Z",
        total_processed=3,
        total_skipped=1,
    )
    pages = {
        "resume-token": ([{"id": "m4"}], None),
    }
    gmail_client = _FakeGmailClient(pages)

    class _Engine:
        async def classify_message(self, _message_id: str) -> _Result:
            return _Result(skipped=False)

    db = _FakeDatabase(initial_state=interrupted)
    backfill = BackfillEngine(
        gmail_client=gmail_client,
        engine=_Engine(),
        db=db,
        config=_processing_config(concurrency=2),
        metrics=_FakeMetrics(),
    )

    await backfill.run()

    assert gmail_client.calls[0][0] == "resume-token"
    assert db.saved_states[-1].status == "completed"
    assert db.saved_states[-1].total_processed == 4


@pytest.mark.asyncio
async def test_run_resumes_from_last_message_id_within_page() -> None:
    interrupted = BackfillState(
        id=9,
        last_page_token="resume-token",
        last_message_id="m4",
        status="interrupted",
        started_at="2026-04-15T00:00:00Z",
        completed_at="2026-04-15T00:01:00Z",
        total_processed=4,
        total_skipped=0,
    )
    pages = {
        "resume-token": ([{"id": "m3"}, {"id": "m4"}, {"id": "m5"}, {"id": "m6"}], None),
    }
    gmail_client = _FakeGmailClient(pages)
    processed_ids: list[str] = []

    class _Engine:
        async def classify_message(self, message_id: str) -> _Result:
            processed_ids.append(message_id)
            return _Result(skipped=False)

    db = _FakeDatabase(initial_state=interrupted)
    backfill = BackfillEngine(
        gmail_client=gmail_client,
        engine=_Engine(),
        db=db,
        config=_processing_config(concurrency=2),
        metrics=_FakeMetrics(),
    )

    await backfill.run()

    assert processed_ids == ["m5", "m6"]
    assert db.saved_states[-1].status == "completed"
    assert db.saved_states[-1].total_processed == 6


@pytest.mark.asyncio
async def test_run_logs_progress_with_explicit_total_estimate_source(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pages = {
        None: ([{"id": "m1"}, {"id": "m2"}, {"id": "m3"}], None),
    }
    gmail_client = _FakeGmailClient(pages)

    class _Engine:
        async def classify_message(self, _message_id: str) -> _Result:
            return _Result(skipped=False)

    db = _FakeDatabase()
    backfill = BackfillEngine(
        gmail_client=gmail_client,
        engine=_Engine(),
        db=db,
        config=_processing_config(concurrency=2, progress_interval=2),
        metrics=_FakeMetrics(),
    )

    with caplog.at_level("INFO"):
        await backfill.run()

    progress_logs = [
        record.getMessage() for record in caplog.records if "Backfill progress:" in record.getMessage()
    ]
    assert any("Backfill progress: 2/unknown" in message for message in progress_logs)
    assert any("estimate_source=gmail_api_result_size_unavailable" in message for message in progress_logs)


@pytest.mark.asyncio
async def test_process_batch_honors_backfill_concurrency_limit() -> None:
    gmail_client = _FakeGmailClient({None: ([], None)})
    current = 0
    max_seen = 0

    class _Engine:
        async def classify_message(self, _message_id: str) -> _Result:
            nonlocal current
            nonlocal max_seen
            current += 1
            max_seen = max(max_seen, current)
            await asyncio.sleep(0.01)
            current -= 1
            return _Result(skipped=False)

    backfill = BackfillEngine(
        gmail_client=gmail_client,
        engine=_Engine(),
        db=_FakeDatabase(),
        config=_processing_config(concurrency=2),
        metrics=_FakeMetrics(),
    )

    processed, skipped = await backfill._process_batch(["m1", "m2", "m3", "m4"])

    assert processed == 4
    assert skipped == 0
    assert max_seen <= 2


@pytest.mark.asyncio
async def test_run_marks_interrupted_when_cancelled() -> None:
    pages = {
        None: ([{"id": "m1"}], None),
    }
    gmail_client = _FakeGmailClient(pages)

    class _Engine:
        async def classify_message(self, _message_id: str) -> _Result:
            raise asyncio.CancelledError()

    db = _FakeDatabase()
    backfill = BackfillEngine(
        gmail_client=gmail_client,
        engine=_Engine(),
        db=db,
        config=_processing_config(concurrency=1),
        metrics=_FakeMetrics(),
    )

    with pytest.raises(asyncio.CancelledError):
        await backfill.run()

    assert db.saved_states[-1].status == "interrupted"
