"""Unit tests for classification engine orchestration."""

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
from gmail_sorter.db.repository import ClassificationRecord
from gmail_sorter.processor.prompt_builder import PromptBuilder


def _config(dry_run: bool = False, threshold: float = 0.7) -> AppConfig:
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
            confidence_threshold=threshold,
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


class _FakeDatabase:
    def __init__(self, classified_message_ids: set[str] | None = None) -> None:
        self.classified_message_ids = classified_message_ids or set()
        self.records: list[ClassificationRecord] = []
        self.dlq_entries: list[object] = []

    def is_classified(self, message_id: str) -> bool:
        return message_id in self.classified_message_ids

    def upsert_classification(self, record: ClassificationRecord) -> None:
        self.records.append(record)
        self.classified_message_ids.add(record.message_id)

    def add_to_dlq(self, entry: object) -> None:
        self.dlq_entries.append(entry)


class _Counter:
    def __init__(self) -> None:
        self.count = 0

    def inc(self) -> None:
        self.count += 1


class _LabelCounter:
    def __init__(self) -> None:
        self.by_category: dict[str, int] = {}

    def labels(self, **kwargs: str) -> "_LabelCounterProxy":
        label = kwargs.get("category") or kwargs.get("error_type")
        if label is None:
            raise ValueError("Expected category or error_type label")
        return _LabelCounterProxy(self.by_category, str(label))


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
        self.classification_errors_total = _LabelCounter()


class _FailingLlmClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def classify(self, system_prompt: str, user_prompt: str) -> _FakeLlmResponse:
        _ = (system_prompt, user_prompt)
        raise self._exc


def _raw_message(message_id: str = "msg-1", label_ids: list[str] | None = None) -> dict:
    label_ids = label_ids or ["INBOX"]
    body = "classification body"
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
            "body": {
                "data": (
                    "Y2xhc3NpZmljYXRpb24gYm9keQ==" if body == "classification body" else body
                )
            },
        },
    }


@pytest.mark.asyncio
async def test_classify_message_happy_path() -> None:
    config = _config(dry_run=False)
    gmail_client = _FakeGmailClient(_raw_message())
    llm_client = _FakeLlmClient(
        json.dumps(
            {
                "category": "alerts",
                "confidence": 0.95,
                "reasoning": "Service notification.",
            }
        )
    )
    database = _FakeDatabase()
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

    result = await engine.classify_message("msg-1")

    assert result.message_id == "msg-1"
    assert result.category == "alerts"
    assert result.confidence == 0.95
    assert result.label_applied == "Label_alerts"
    assert result.skipped is False
    assert len(database.records) == 1
    assert gmail_client.applied == [("msg-1", "Label_alerts", False)]
    assert metrics.emails_processed_total.count == 1
    assert metrics.emails_classified_total.by_category["alerts"] == 1
    assert llm_client.calls == 1


@pytest.mark.asyncio
async def test_classify_message_uses_fallback_for_low_confidence() -> None:
    config = _config(dry_run=False, threshold=0.7)
    gmail_client = _FakeGmailClient(_raw_message())
    llm_client = _FakeLlmClient(
        json.dumps(
            {
                "category": "alerts",
                "confidence": 0.2,
                "reasoning": "Uncertain.",
            }
        )
    )
    database = _FakeDatabase()
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

    result = await engine.classify_message("msg-1")

    assert result.category == "uncategorized"
    assert result.label_applied == "Label_uncategorized"
    assert gmail_client.applied == [("msg-1", "Label_uncategorized", False)]


@pytest.mark.asyncio
async def test_classify_message_dry_run_skips_gmail_and_db_write() -> None:
    config = _config(dry_run=True)
    gmail_client = _FakeGmailClient(_raw_message())
    llm_client = _FakeLlmClient(
        json.dumps(
            {
                "category": "alerts",
                "confidence": 0.9,
                "reasoning": "Service notification.",
            }
        )
    )
    database = _FakeDatabase()
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

    result = await engine.classify_message("msg-1")

    assert result.skipped is False
    assert gmail_client.applied == []
    assert database.records == []
    assert llm_client.calls == 1


@pytest.mark.asyncio
async def test_classify_message_skips_when_already_classified() -> None:
    config = _config(dry_run=False)
    gmail_client = _FakeGmailClient(_raw_message())
    llm_client = _FakeLlmClient(
        json.dumps(
            {
                "category": "alerts",
                "confidence": 0.95,
                "reasoning": "Service notification.",
            }
        )
    )
    database = _FakeDatabase(classified_message_ids={"msg-1"})
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

    result = await engine.classify_message("msg-1")

    assert result.skipped is True
    assert result.category == ""
    assert gmail_client.applied == []
    assert database.records == []
    assert llm_client.calls == 0


@pytest.mark.asyncio
async def test_classify_message_skips_blocklisted_sender_domain() -> None:
    config = _config(dry_run=False)
    config.classification.blocklist = ["example.com"]

    gmail_client = _FakeGmailClient(_raw_message())
    llm_client = _FakeLlmClient(
        json.dumps(
            {
                "category": "alerts",
                "confidence": 0.95,
                "reasoning": "Service notification.",
            }
        )
    )
    database = _FakeDatabase()
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

    result = await engine.classify_message("msg-1")

    assert result.skipped is True
    assert result.category == ""
    assert llm_client.calls == 0
    assert gmail_client.applied == []
    assert database.records == []


@pytest.mark.asyncio
async def test_classify_message_blocklist_skip_logs_structured_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sender-policy skips should include structured operation context fields."""

    config = _config(dry_run=False)
    config.classification.blocklist = ["example.com"]

    gmail_client = _FakeGmailClient(_raw_message())
    llm_client = _FakeLlmClient(
        json.dumps(
            {
                "category": "alerts",
                "confidence": 0.95,
                "reasoning": "Service notification.",
            }
        )
    )
    database = _FakeDatabase()
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

    with caplog.at_level("INFO"):
        result = await engine.classify_message("msg-1")

    assert result.skipped is True
    matching = [
        record
        for record in caplog.records
        if "Skipping message due to sender domain policy" in record.getMessage()
    ]
    assert matching
    context = getattr(matching[-1], "context", {})
    assert context.get("operation") == "classify_message"
    assert context.get("message_id") == "msg-1"
    assert context.get("outcome") == "skip"


@pytest.mark.asyncio
async def test_classify_message_skips_sender_not_in_allowlist() -> None:
    config = _config(dry_run=False)
    config.classification.allowlist = ["allow.example"]

    gmail_client = _FakeGmailClient(_raw_message())
    llm_client = _FakeLlmClient(
        json.dumps(
            {
                "category": "alerts",
                "confidence": 0.95,
                "reasoning": "Service notification.",
            }
        )
    )
    database = _FakeDatabase()
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

    result = await engine.classify_message("msg-1")

    assert result.skipped is True
    assert result.category == ""
    assert llm_client.calls == 0
    assert gmail_client.applied == []


@pytest.mark.asyncio
async def test_classify_message_multi_label_applies_all_resolved_labels() -> None:
    """Multi-label mode should apply one label per resolved category."""

    config = _config(dry_run=False)
    config.classification.multi_label = True
    config.categories.append(
        CategoryConfig(
            name="billing",
            label="AutoSort/Billing",
            description="Billing notifications",
        )
    )

    gmail_client = _FakeGmailClient(_raw_message())
    llm_client = _FakeLlmClient(
        json.dumps(
            {
                "categories": [
                    {
                        "category": "alerts",
                        "confidence": 0.91,
                        "reasoning": "Operational notification.",
                    },
                    {
                        "category": "billing",
                        "confidence": 0.88,
                        "reasoning": "Invoice or charge event.",
                    },
                ]
            }
        )
    )
    database = _FakeDatabase()
    metrics = _FakeMetrics()
    checker = IdempotencyChecker(database, system_label_ids={"Label_alerts", "Label_billing"})
    builder = PromptBuilder(config.llm, config.categories)

    engine = ClassificationEngine(
        config=config,
        gmail_client=gmail_client,
        llm_client=llm_client,
        db=database,
        label_map={
            "alerts": "Label_alerts",
            "billing": "Label_billing",
            "uncategorized": "Label_uncategorized",
        },
        idempotency_checker=checker,
        prompt_builder=builder,
        metrics=metrics,
    )

    result = await engine.classify_message("msg-1")

    assert result.skipped is False
    assert result.category == "alerts"
    assert result.label_applied == "Label_alerts"
    assert gmail_client.applied == [
        ("msg-1", "Label_alerts", False),
        ("msg-1", "Label_billing", False),
    ]
    assert len(database.records) == 1
    assert database.records[0].category == "alerts,billing"
    assert database.records[0].label_applied == "Label_alerts,Label_billing"
    assert metrics.emails_classified_total.by_category["alerts"] == 1
    assert metrics.emails_classified_total.by_category["billing"] == 1


@pytest.mark.asyncio
async def test_classify_message_sends_critical_webhook_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Critical classification failures should emit PRD-compliant webhook payloads."""

    payloads: list[dict[str, object]] = []

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return

    class _FakeAsyncClient:
        def __init__(self, timeout: float, verify: object) -> None:
            _ = (timeout, verify)

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            _ = (exc_type, exc, tb)

        async def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
            payloads.append({"url": url, **json})
            return _FakeResponse()

    monkeypatch.setattr("gmail_sorter.classifier.engine.httpx.AsyncClient", _FakeAsyncClient)

    config = _config(dry_run=False)
    config.alerts.webhook_url = "https://hooks.example.test/critical"
    gmail_client = _FakeGmailClient(_raw_message())
    llm_client = _FailingLlmClient(TimeoutError("llm timeout"))
    database = _FakeDatabase()
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

    with pytest.raises(TimeoutError):
        await engine.classify_message("msg-1")

    assert len(payloads) == 1
    assert payloads[0]["url"] == "https://hooks.example.test/critical"
    assert payloads[0]["error_type"] == "llm_error"
    assert payloads[0]["message_id"] == "msg-1"
    assert payloads[0]["description"] == "llm timeout"
    assert "timestamp" in payloads[0]
    assert database.dlq_entries
    assert metrics.classification_errors_total.by_category["llm_error"] == 1


def test_error_type_mapping_uses_prd_taxonomy() -> None:
    """Exception mapping should always resolve to required PRD error types."""

    class OAuthFailure(Exception):
        pass

    class PubSubDeliveryError(Exception):
        pass

    assert ClassificationEngine._error_type(OAuthFailure("auth failed")) == "auth_error"
    assert ClassificationEngine._error_type(PubSubDeliveryError("pubsub failed")) == "pubsub_error"
    assert ClassificationEngine._error_type(TimeoutError("timed out")) == "llm_error"
    assert ClassificationEngine._error_type(SystemExit(1)) == "config_error"
    assert ClassificationEngine._error_type(RuntimeError("unknown")) == "api_error"
