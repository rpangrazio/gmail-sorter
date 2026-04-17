"""Integration tests for classification pipeline composition."""

from __future__ import annotations

import json
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


def _config(dry_run: bool = False) -> AppConfig:
    return AppConfig(
        gmail=GmailConfig(
            credentials_path="./credentials.json",
            token_path="./token.json",
            scopes=["scope-1", "scope-2"],
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
            system_prompt="System prompt",
            prompt_template=(
                "From: {{ sender }} | Subject: {{ subject }} | "
                "Category: {{ categories[0].name }}"
            ),
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
                description="Service alerts",
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
            dry_run=dry_run,
        ),
        logging=LoggingConfig(level="INFO", log_prompts=False),
        database=DatabaseConfig(path=":memory:"),
    )


class _FakeGmailClient:
    def __init__(self, raw_message: dict) -> None:
        self._raw_message = raw_message
        self.applied: list[tuple[str, str, bool]] = []

    def get_message(self, message_id: str) -> dict:
        assert message_id == self._raw_message["id"]
        return self._raw_message

    def apply_label(self, message_id: str, label_id: str, archive: bool = False) -> None:
        self.applied.append((message_id, label_id, archive))


@dataclass
class _FakeLlmResponse:
    raw: str


class _FakeLlmClient:
    def __init__(self, raw_response: str) -> None:
        self._raw_response = raw_response
        self.calls = 0

    async def classify(self, system_prompt: str, user_prompt: str) -> _FakeLlmResponse:
        assert system_prompt
        assert user_prompt
        self.calls += 1
        return _FakeLlmResponse(raw=self._raw_response)


class _Counter:
    def __init__(self) -> None:
        self.count = 0

    def inc(self) -> None:
        self.count += 1


class _LabelCounter:
    def __init__(self) -> None:
        self.by_category: dict[str, int] = {}

    def labels(self, category: str) -> "_LabelCounterProxy":
        return _LabelCounterProxy(self.by_category, category)


class _LabelCounterProxy:
    def __init__(self, store: dict[str, int], category: str) -> None:
        self._store = store
        self._category = category

    def inc(self) -> None:
        self._store[self._category] = self._store.get(self._category, 0) + 1


class _FakeMetrics:
    def __init__(self) -> None:
        self.emails_processed_total = _Counter()
        self.emails_classified_total = _LabelCounter()
        self.llm_latency_seconds = _LatencyHistogram()


class _LatencyHistogram:
    def __init__(self) -> None:
        self.values: list[float] = []

    def observe(self, value: float) -> None:
        self.values.append(value)


def _raw_message(message_id: str = "msg-1", label_ids: list[str] | None = None) -> dict:
    label_ids = label_ids or ["INBOX"]
    return {
        "id": message_id,
        "threadId": "thread-1",
        "labelIds": label_ids,
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "Subject", "value": "Subject"},
                {"name": "Date", "value": "Wed, 15 Apr 2026 00:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "Y2xhc3NpZmljYXRpb24gYm9keQ=="},
        },
    }


def _build_engine(config: AppConfig, raw_message: dict, raw_llm_response: str):
    database = Database(":memory:")
    database.initialize()
    gmail_client = _FakeGmailClient(raw_message)
    llm_client = _FakeLlmClient(raw_llm_response)
    metrics = _FakeMetrics()
    checker = IdempotencyChecker(database, system_label_ids={"Label_alerts"})
    builder = PromptBuilder(config.llm, config.categories)

    engine = ClassificationEngine(
        config=config,
        gmail_client=gmail_client,
        llm_client=llm_client,
        db=database,
        label_map={"alerts": "Label_alerts", "uncategorized": "Label_uncategorized"},
        idempotency_checker=checker,
        prompt_builder=builder,
        metrics=metrics,
    )
    return engine, gmail_client, llm_client, database, metrics


@pytest.mark.asyncio
async def test_classify_message_applies_label_and_writes_db() -> None:
    """A full classification run should label the message and persist a record."""

    engine, gmail_client, llm_client, database, metrics = _build_engine(
        config=_config(dry_run=False),
        raw_message=_raw_message(),
        raw_llm_response=json.dumps(
            {
                "category": "alerts",
                "confidence": 0.91,
                "reasoning": "Service notification.",
            }
        ),
    )

    result = await engine.classify_message("msg-1")

    assert result.skipped is False
    assert result.category == "alerts"
    assert gmail_client.applied == [("msg-1", "Label_alerts", False)]
    assert database.get_classification("msg-1") is not None
    assert llm_client.calls == 1
    assert len(metrics.llm_latency_seconds.values) == 1
    assert metrics.llm_latency_seconds.values[0] >= 0.0


@pytest.mark.asyncio
async def test_repeat_classification_is_skipped_by_idempotency() -> None:
    """Reprocessing a message should skip after the first successful write."""

    engine, gmail_client, llm_client, database, _metrics = _build_engine(
        config=_config(dry_run=False),
        raw_message=_raw_message(),
        raw_llm_response=json.dumps(
            {
                "category": "alerts",
                "confidence": 0.88,
                "reasoning": "Service notification.",
            }
        ),
    )

    first = await engine.classify_message("msg-1")
    second = await engine.classify_message("msg-1")

    assert first.skipped is False
    assert second.skipped is True
    assert llm_client.calls == 1
    assert len(gmail_client.applied) == 1
    assert database.get_classification("msg-1") is not None


@pytest.mark.asyncio
async def test_dry_run_skips_label_application_and_db_write() -> None:
    """Dry-run classification should not modify Gmail state or persistence."""

    engine, gmail_client, llm_client, database, _metrics = _build_engine(
        config=_config(dry_run=True),
        raw_message=_raw_message(),
        raw_llm_response=json.dumps(
            {
                "category": "alerts",
                "confidence": 0.9,
                "reasoning": "Service notification.",
            }
        ),
    )

    result = await engine.classify_message("msg-1")

    assert result.skipped is False
    assert gmail_client.applied == []
    assert database.get_classification("msg-1") is None
    assert llm_client.calls == 1
