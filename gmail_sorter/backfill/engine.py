"""Mailbox backfill orchestration with resume and concurrency controls."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from gmail_sorter.config.models import ProcessingConfig
from gmail_sorter.db.repository import BackfillState, Database

LOGGER = logging.getLogger(__name__)


class BackfillEngine:
    """Run full-mailbox backfill classification with resumable state."""

    def __init__(
        self,
        gmail_client: Any,
        engine: Any,
        db: Database,
        config: ProcessingConfig,
        metrics: Any,
    ) -> None:
        """Initialize backfill dependencies and runtime options."""

        self._gmail_client = gmail_client
        self._engine = engine
        self._db = db
        self._config = config
        self._metrics = metrics

    async def run(self) -> None:
        """Execute mailbox backfill until all pages are processed."""

        state = self._initialize_state()
        page_token = state.last_page_token
        progress_interval = int(getattr(self._config, "backfill_progress_interval", 100))
        if progress_interval <= 0:
            progress_interval = 100
        next_progress_log = ((state.total_processed // progress_interval) + 1) * progress_interval

        try:
            while True:
                messages, next_page_token = self._gmail_client.list_messages(
                    page_token=page_token,
                    batch_size=self._config.batch_size,
                )
                message_ids = [
                    str(message["id"])
                    for message in messages
                    if isinstance(message, dict) and message.get("id")
                ]

                resumed_message_ids = self._messages_after_last_processed(
                    message_ids,
                    state.last_message_id,
                )

                state.status = "running"
                state.last_page_token = page_token
                self._db.upsert_backfill_state(state)

                await self._process_batch_with_state(
                    message_ids=resumed_message_ids,
                    state=state,
                    page_token=page_token,
                    progress_interval=progress_interval,
                    next_progress_log=next_progress_log,
                )

                next_progress_log = ((state.total_processed // progress_interval) + 1) * progress_interval

                if message_ids:
                    state.last_message_id = message_ids[-1]
                state.last_page_token = next_page_token
                state.status = "running"
                self._db.upsert_backfill_state(state)

                if next_page_token is None:
                    break

                page_token = next_page_token

            state.status = "completed"
            state.last_page_token = None
            state.completed_at = self._utc_now_iso()
            self._db.upsert_backfill_state(state)
        except asyncio.CancelledError:
            state.status = "interrupted"
            state.completed_at = self._utc_now_iso()
            self._db.upsert_backfill_state(state)
            raise

    async def _process_batch(self, message_ids: list[str]) -> tuple[int, int]:
        """Backward-compatible wrapper for processing without state persistence."""

        state = BackfillState(
            id=None,
            last_page_token=None,
            last_message_id=None,
            status="running",
            started_at=self._utc_now_iso(),
            completed_at=None,
            total_processed=0,
            total_skipped=0,
        )
        await self._process_batch_with_state(
            message_ids=message_ids,
            state=state,
            page_token=None,
            progress_interval=max(1, self._config.backfill_progress_interval),
            next_progress_log=max(1, self._config.backfill_progress_interval),
        )
        return state.total_processed, state.total_skipped

    async def _process_batch_with_state(
        self,
        message_ids: list[str],
        state: BackfillState,
        page_token: str | None,
        progress_interval: int,
        next_progress_log: int,
    ) -> None:
        """Process one page of message IDs with bounded concurrency and durable progress."""

        if not message_ids:
            return

        limit = max(1, self._config.backfill_concurrency)
        semaphore = asyncio.Semaphore(limit)
        completion_results: dict[int, bool] = {}
        next_commit_index = 0

        async def classify_one(index: int, message_id: str) -> tuple[int, bool]:
            async with semaphore:
                result = await self._engine.classify_message(message_id)
            return index, bool(getattr(result, "skipped", False))

        tasks = [
            asyncio.create_task(classify_one(index, message_id))
            for index, message_id in enumerate(message_ids)
        ]

        for task in asyncio.as_completed(tasks):
            index, skipped = await task
            completion_results[index] = skipped

            while next_commit_index in completion_results:
                committed_skipped = completion_results.pop(next_commit_index)
                committed_message_id = message_ids[next_commit_index]
                state.total_processed += 1
                if committed_skipped:
                    state.total_skipped += 1
                state.last_message_id = committed_message_id
                state.last_page_token = page_token
                state.status = "running"
                self._db.upsert_backfill_state(state)

                while state.total_processed >= next_progress_log:
                    LOGGER.info(
                        "Backfill progress: %s/%s (estimate_source=%s)",
                        state.total_processed,
                        "unknown",
                        "gmail_api_result_size_unavailable",
                    )
                    next_progress_log += progress_interval

                next_commit_index += 1

    @staticmethod
    def _messages_after_last_processed(
        message_ids: list[str],
        last_message_id: str | None,
    ) -> list[str]:
        """Return message IDs after the last durably processed message ID."""

        if not message_ids or not last_message_id:
            return message_ids
        if last_message_id not in message_ids:
            return message_ids
        resume_index = message_ids.index(last_message_id) + 1
        return message_ids[resume_index:]

    def _initialize_state(self) -> BackfillState:
        """Return resumable state or initialize a fresh run state."""

        existing = self._db.get_latest_backfill_state()
        if existing is not None and existing.status in {"running", "interrupted"}:
            existing.status = "running"
            existing.completed_at = None
            self._db.upsert_backfill_state(existing)
            return existing

        state = BackfillState(
            id=None,
            last_page_token=None,
            last_message_id=None,
            status="running",
            started_at=self._utc_now_iso(),
            completed_at=None,
            total_processed=0,
            total_skipped=0,
        )
        self._db.upsert_backfill_state(state)
        return state

    @staticmethod
    def _utc_now_iso() -> str:
        """Return the current UTC timestamp in ISO-8601 format."""

        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
