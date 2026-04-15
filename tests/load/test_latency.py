"""Load test validating end-to-end classification latency."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

import pytest

from gmail_sorter.classifier.engine import ClassificationEngine
from gmail_sorter.classifier.idempotency import IdempotencyChecker
from gmail_sorter.config.models import (
    AppConfig,
    CategoryConfig,
    ClassificationConfig,
    DatabaseConfig,
    GmailConfig,
    LlmConfig,
    LoggingConfig,
    ProcessingConfig,
    PubSubConfig,
)
from gmail_sorter.db.repository import Database
from gmail_sorter.processor.prompt_builder import PromptBuilder


def _config() -> AppConfig:
    """Create an app config fixture suitable for latency testing."""

    return AppConfig(
        gmail=GmailConfig(
            credentials_path="./credentials.json",
            token_path="./token.json",
            scopes=["scope-1"],
        ),
        pubsub=PubSubConfig(
            project_id="proj",
            topic="topic",
            subscription="sub",
            mode="pull",
        ),
        llm=LlmConfig(
            provider="github_copilot",
            model="gpt-4o",
            api_key_env="GITHUB_COPILOT_API_KEY",
            timeout_seconds=30,
            max_retries=1,
            system_prompt="System",
            prompt_template="Subject: {{ subject }} Body: {{ body }}",
        ),
        classification=ClassificationConfig(
            confidence_threshold=0.7,
            fallback_category="uncategorized",
            multi_label=False,
        ),
        categories=[
            CategoryConfig(
                name="alerts",
                label="AutoSort/Alerts",
                description="Alerts",
            ),
            CategoryConfig(
                name="uncategorized",
                label="AutoSort/Uncategorized",
                description="Fallback",
            ),
        ],
        processing=ProcessingConfig(
            body_max_length=4096,
            batch_size=50,
            backfill_concurrency=5,
            archive_after_label=False,
            dry_run=False,
        ),
        logging=LoggingConfig(level="INFO", log_prompts=False),
        database=DatabaseConfig(path=":memory:"),
    )


class _FakeGmailClient:
    """Return a stable message payload and capture applied labels."""

    def __init__(self) -> None:
        self.applied: list[tuple[str, str, bool]] = []

    def get_message(self, message_id: str) -> dict:
        return {
            "id": message_id,
            "threadId": "thread-1",
            "labelIds": ["INBOX"],
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "Subject", "value": "Latency test"},
                    {"name": "Date", "value": "Wed, 15 Apr 2026 00:00:00 +0000"},
                ],
                "mimeType": "text/plain",
                "body": {"data": "TG9hZCB0ZXN0IGJvZHk="},
            },
        }

    def apply_label(self, message_id: str, label_id: str, archive: bool = False) -> None:
        self.applied.append((message_id, label_id, archive))


@dataclass(slots=True)
class _FakeLlmResponse:
    raw: str


class _FakeLlmClient:
    """Return a fixed successful response after 100ms delay."""

    async def classify(self, _system_prompt: str, _user_prompt: str) -> _FakeLlmResponse:
        await asyncio.sleep(0.1)
        return _FakeLlmResponse(
            raw=json.dumps(
                {
                    "category": "alerts",
                    "confidence": 0.95,
                    "reasoning": "Operational alert.",
                }
            )
        )


class _Counter:
    def __init__(self) -> None:
        self.count = 0

    def inc(self) -> None:
        self.count += 1


class _LabelCounter:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def labels(self, category: str):
        counter = self

        class _Proxy:
            def inc(self) -> None:
                counter.counts[category] = counter.counts.get(category, 0) + 1

        return _Proxy()


class _FakeMetrics:
    def __init__(self) -> None:
        self.emails_processed_total = _Counter()
        self.emails_classified_total = _LabelCounter()


@pytest.mark.asyncio
async def test_classify_message_latency_under_10_seconds() -> None:
    """End-to-end classification latency should satisfy NFR-001 target."""

    config = _config()
    database = Database(":memory:")
    database.initialize()
    try:
        gmail_client = _FakeGmailClient()
        engine = ClassificationEngine(
            config=config,
            gmail_client=gmail_client,
            llm_client=_FakeLlmClient(),
            db=database,
            label_map={"alerts": "Label_alerts", "uncategorized": "Label_uncategorized"},
            idempotency_checker=IdempotencyChecker(database, system_label_ids={"Label_alerts"}),
            prompt_builder=PromptBuilder(config.llm, config.categories),
            metrics=_FakeMetrics(),
        )

        started = time.perf_counter()
        result = await engine.classify_message("latency-message")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
    finally:
        database.close()

    assert result.skipped is False
    assert gmail_client.applied
    assert elapsed_ms < 10_000
