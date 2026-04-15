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

                processed_count, skipped_count = await self._process_batch(message_ids)

                state.total_processed += processed_count
                state.total_skipped += skipped_count
                if message_ids:
                    state.last_message_id = message_ids[-1]
                state.last_page_token = next_page_token
                state.status = "running"
                self._db.upsert_backfill_state(state)

                while state.total_processed >= next_progress_log:
                    estimated = state.total_processed if next_page_token is None else state.total_processed + len(message_ids)
                    LOGGER.info(
                        "Backfill progress: %s/%s",
                        state.total_processed,
                        estimated,
                    )
                    next_progress_log += progress_interval

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
        """Process one page of message IDs with bounded concurrency."""

        if not message_ids:
            return 0, 0

        processed = 0
        skipped = 0
        limit = max(1, self._config.backfill_concurrency)
        semaphore = asyncio.Semaphore(limit)

        async def classify_one(message_id: str) -> None:
            nonlocal processed, skipped

            async with semaphore:
                result = await self._engine.classify_message(message_id)

            processed += 1
            if getattr(result, "skipped", False):
                skipped += 1

        async with asyncio.TaskGroup() as task_group:
            for message_id in message_ids:
                task_group.create_task(classify_one(message_id))

        return processed, skipped

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
