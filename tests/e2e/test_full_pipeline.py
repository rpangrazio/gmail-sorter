"""End-to-end style tests for CLI-driven single-message processing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import respx
from click.testing import CliRunner

from gmail_sorter.classifier.engine import ClassificationEngine
from gmail_sorter.classifier.idempotency import IdempotencyChecker
from gmail_sorter.cli import main
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
from gmail_sorter.processor.prompt_builder import PromptBuilder


def _config(database_path: Path) -> AppConfig:
    """Build a minimal PRD-aligned app config for end-to-end tests."""

    return AppConfig(
        gmail=GmailConfig(
            credentials_path="./credentials.json",
            token_path="./token.json",
            scopes=["scope-1"],
        ),
        pubsub=PubSubConfig(
            project_id="project",
            topic="topic",
            subscription="subscription",
            mode="pull",
        ),
        llm=LlmConfig(
            provider="openai_compatible",
            model="gpt-4o",
            api_key_env="OPENAI_API_KEY",
            timeout_seconds=5,
            max_retries=1,
            system_prompt="System",
            prompt_template="From {{ sender }} | {{ subject }} | {{ body }}",
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
                description="Operational notifications",
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
            backfill_concurrency=2,
            archive_after_label=False,
            dry_run=False,
        ),
        logging=LoggingConfig(level="INFO", log_prompts=False),
        database=DatabaseConfig(path=str(database_path)),
    )


def _gmail_message(message_id: str = "msg-1") -> dict[str, Any]:
    """Return a compact Gmail message payload with plain-text body."""

    return {
        "id": message_id,
        "threadId": "thread-1",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "Subject", "value": "Important alert"},
                {"name": "Date", "value": "Wed, 15 Apr 2026 00:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "U2VydmljZSB3YXJuaW5n"},
        },
    }


class _FakeGmailClient:
    """Minimal Gmail client used by watcher and classification engine."""

    def __init__(self) -> None:
        self.applied: list[tuple[str, str, bool]] = []

    def register_watch(self, _topic_name: str) -> dict[str, str]:
        return {"historyId": "1"}

    def get_message(self, message_id: str) -> dict[str, Any]:
        return _gmail_message(message_id)

    def apply_label(self, message_id: str, label_id: str, archive: bool = False) -> None:
        self.applied.append((message_id, label_id, archive))


class _FakeLlmClient:
    """LLM stub that returns configured payload or raises an error."""

    def __init__(self, raw_response: str | None = None, error: Exception | None = None) -> None:
        self._raw_response = raw_response
        self._error = error

    async def classify(self, _system_prompt: str, _user_prompt: str) -> Any:
        if self._error is not None:
            raise self._error
        return _RawResponse(raw=self._raw_response or "{}")

    async def close(self) -> None:
        return


@dataclass(slots=True)
class _RawResponse:
    raw: str


class _Counter:
    """Simple counter compatible with Prometheus-style `inc()`."""

    def __init__(self) -> None:
        self.value = 0

    def inc(self) -> None:
        self.value += 1


class _LabelCounter:
    """Simple labeled counter compatible with `.labels(...).inc()`."""

    def __init__(self) -> None:
        self.by_key: dict[str, int] = {}

    def labels(self, **kwargs: str) -> "_LabelCounterProxy":
        key = next(iter(kwargs.values())) if kwargs else ""
        return _LabelCounterProxy(self.by_key, key)


class _LabelCounterProxy:
    """Proxy used to increment a specific labeled counter key."""

    def __init__(self, store: dict[str, int], key: str) -> None:
        self._store = store
        self._key = key

    def inc(self) -> None:
        self._store[self._key] = self._store.get(self._key, 0) + 1


class _FakeMetrics:
    """Metrics collector stub used by CLI runtime wiring."""

    def __init__(self) -> None:
        self.emails_processed_total = _Counter()
        self.emails_classified_total = _LabelCounter()
        self.classification_errors_total = _LabelCounter()

    def start_http_server(self, port: int = 9090) -> None:
        _ = port


class _FakeHealthServer:
    """Health server stub used to avoid binding network ports during tests."""

    def __init__(self, port: int = 8080) -> None:
        self.port = port

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def set_healthy(self, last_message_at: str | None = None) -> None:
        _ = last_message_at


class _FakeWatcher:
    """Watcher stub used by CLI run workflow."""

    def __init__(self, gmail_client: _FakeGmailClient, config: PubSubConfig) -> None:
        self.gmail_client = gmail_client
        self.config = config

    def register(self) -> dict[str, str]:
        topic = f"projects/{self.config.project_id}/topics/{self.config.topic}"
        return self.gmail_client.register_watch(topic)

    def schedule_renewal(self) -> None:
        return

    def stop(self) -> None:
        return


class _FakeListener:
    """Listener stub that simulates one pull notification then exits."""

    def __init__(self, config: PubSubConfig, engine: ClassificationEngine, metrics: _FakeMetrics) -> None:
        self.config = config
        self.engine = engine
        self.metrics = metrics

    async def start(self) -> None:
        self.metrics.pubsub_messages_received_total = _Counter()
        try:
            await self.engine.classify_message("msg-1")
        except Exception:
            return

    async def stop(self) -> None:
        return


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch network-bound runtime dependencies with local test doubles."""

    monkeypatch.setattr("gmail_sorter.observability.configure_logging", lambda *_args: None)
    monkeypatch.setattr("gmail_sorter.observability.health.HealthServer", _FakeHealthServer)
    monkeypatch.setattr("gmail_sorter.pubsub.listener.PubSubListener", _FakeListener)
    monkeypatch.setattr("gmail_sorter.pubsub.watcher.GmailWatcher", _FakeWatcher)


def _build_engine_for_cli(
    config: AppConfig,
    db: Any,
    gmail_client: _FakeGmailClient,
    llm_client: _FakeLlmClient,
) -> tuple[ClassificationEngine, _FakeGmailClient, _FakeLlmClient, _FakeMetrics]:
    """Construct a real classification engine using fake external integrations."""

    metrics = _FakeMetrics()
    prompt_builder = PromptBuilder(config.llm, config.categories)
    checker = IdempotencyChecker(db=db, system_label_ids={"Label_alerts", "Label_uncategorized"})
    engine = ClassificationEngine(
        config=config,
        gmail_client=gmail_client,
        llm_client=llm_client,
        db=db,
        label_map={
            "alerts": "Label_alerts",
            "uncategorized": "Label_uncategorized",
        },
        idempotency_checker=checker,
        prompt_builder=prompt_builder,
        metrics=metrics,
    )
    return engine, gmail_client, llm_client, metrics


@respx.mock
def test_run_classifies_single_message_and_applies_label(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`run` should process one message and apply the mapped label."""

    _patch_runtime(monkeypatch)
    config = _config(tmp_path / "e2e-full.db")
    gmail_client = _FakeGmailClient()
    llm_client = _FakeLlmClient(
        raw_response=json.dumps(
            {
                "category": "alerts",
                "confidence": 0.92,
                "reasoning": "Service-related alert.",
            }
        )
    )

    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)
    monkeypatch.setattr(
        "gmail_sorter.cli._build_engine",
        lambda cfg, db: _build_engine_for_cli(cfg, db, gmail_client, llm_client),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["run"])

    assert result.exit_code == 0
    assert gmail_client.applied == [("msg-1", "Label_alerts", False)]


@respx.mock
def test_run_dry_run_makes_no_gmail_modify_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`run --dry-run` should classify but avoid Gmail label mutations."""

    _patch_runtime(monkeypatch)
    config = _config(tmp_path / "e2e-dry-run.db")
    gmail_client = _FakeGmailClient()
    llm_client = _FakeLlmClient(
        raw_response=json.dumps(
            {
                "category": "alerts",
                "confidence": 0.82,
                "reasoning": "Service-related alert.",
            }
        )
    )

    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)
    monkeypatch.setattr(
        "gmail_sorter.cli._build_engine",
        lambda cfg, db: _build_engine_for_cli(cfg, db, gmail_client, llm_client),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["--dry-run", "run"])

    assert result.exit_code == 0
    assert gmail_client.applied == []


@respx.mock
def test_run_unknown_category_routes_to_fallback_label(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unknown LLM categories should map to fallback label application."""

    _patch_runtime(monkeypatch)
    config = _config(tmp_path / "e2e-fallback.db")
    gmail_client = _FakeGmailClient()
    llm_client = _FakeLlmClient(
        raw_response=json.dumps(
            {
                "category": "nonexistent",
                "confidence": 0.99,
                "reasoning": "Unknown category returned by model.",
            }
        )
    )

    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)
    monkeypatch.setattr(
        "gmail_sorter.cli._build_engine",
        lambda cfg, db: _build_engine_for_cli(cfg, db, gmail_client, llm_client),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["run"])

    assert result.exit_code == 0
    assert gmail_client.applied == [("msg-1", "Label_uncategorized", False)]


@respx.mock
def test_run_timeout_records_message_in_dlq(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Classification timeouts should produce a dead-letter queue entry."""

    _patch_runtime(monkeypatch)
    database_path = tmp_path / "e2e-dlq.db"
    config = _config(database_path)
    gmail_client = _FakeGmailClient()
    llm_client = _FakeLlmClient(error=TimeoutError("timed out"))

    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)
    monkeypatch.setattr(
        "gmail_sorter.cli._build_engine",
        lambda cfg, db: _build_engine_for_cli(cfg, db, gmail_client, llm_client),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["run"])

    assert result.exit_code == 0

    from gmail_sorter.db.repository import Database

    db = Database(str(database_path))
    db.initialize()
    try:
        dlq_entries = db.get_dlq_entries(limit=10)
    finally:
        db.close()

    assert dlq_entries
    assert dlq_entries[0].message_id == "msg-1"
    assert dlq_entries[0].error_type == "llm_error"
