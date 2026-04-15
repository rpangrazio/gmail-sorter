"""End-to-end style tests for CLI backfill workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import CliRunner

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
from gmail_sorter.db.repository import BackfillState, ClassificationRecord, Database


def _config(database_path: Path) -> AppConfig:
    """Build a minimal app configuration for backfill CLI tests."""

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
            provider="github_copilot",
            model="gpt-4o",
            api_key_env="GITHUB_COPILOT_API_KEY",
            timeout_seconds=5,
            max_retries=1,
            system_prompt="System",
            prompt_template="Template",
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
            backfill_concurrency=5,
            archive_after_label=False,
            dry_run=False,
        ),
        logging=LoggingConfig(level="INFO", log_prompts=False),
        database=DatabaseConfig(path=str(database_path)),
    )


def _pages(total: int = 250, page_size: int = 50) -> dict[str | None, tuple[list[dict[str, str]], str | None]]:
    """Generate deterministic paginated Gmail list response fixtures."""

    result: dict[str | None, tuple[list[dict[str, str]], str | None]] = {}
    page_count = total // page_size
    for index in range(page_count):
        start = (index * page_size) + 1
        end = start + page_size
        messages = [{"id": f"m{message_id}"} for message_id in range(start, end)]
        token = None if index == 0 else f"p{index}"
        next_token = None if index + 1 == page_count else f"p{index + 1}"
        result[token] = (messages, next_token)
    return result


class _FakeGmailClient:
    """Gmail client stub exposing paginated mailbox listings."""

    def __init__(self, pages: dict[str | None, tuple[list[dict[str, str]], str | None]]) -> None:
        self._pages = pages
        self.calls: list[str | None] = []

    def list_messages(
        self,
        page_token: str | None = None,
        batch_size: int = 50,
    ) -> tuple[list[dict[str, str]], str | None]:
        _ = batch_size
        self.calls.append(page_token)
        return self._pages.get(page_token, ([], None))


@dataclass(slots=True)
class _ClassificationResult:
    skipped: bool


class _FakeEngine:
    """Classifier stub that writes directly to DB and can interrupt."""

    def __init__(self, db: Database, interrupt_after: int | None = None) -> None:
        self._db = db
        self._interrupt_after = interrupt_after
        self._count = 0

    async def classify_message(self, message_id: str) -> _ClassificationResult:
        self._count += 1
        if self._interrupt_after is not None and self._count > self._interrupt_after:
            raise KeyboardInterrupt()

        self._db.upsert_classification(
            ClassificationRecord(
                message_id=message_id,
                gmail_thread_id=f"thread-{message_id}",
                timestamp="2026-04-15T00:00:00Z",
                category="alerts",
                confidence=0.9,
                model_used="gpt-4o",
                prompt_template_hash="hash",
                label_applied="Label_alerts",
                processing_duration_ms=1,
            )
        )
        return _ClassificationResult(skipped=False)


class _FakeLlmClient:
    """No-op LLM client placeholder returned from CLI engine builder."""

    async def close(self) -> None:
        return


class _FakeMetrics:
    """No-op metrics placeholder returned from CLI engine builder."""


def test_backfill_classifies_all_250_messages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`backfill` should process every message across all pages."""

    config = _config(tmp_path / "e2e-backfill-all.db")
    gmail_client = _FakeGmailClient(_pages(total=250, page_size=50))

    monkeypatch.setattr("gmail_sorter.observability.configure_logging", lambda *_args: None)
    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)
    monkeypatch.setattr(
        "gmail_sorter.cli._build_engine",
        lambda _cfg, db: (_FakeEngine(db), gmail_client, _FakeLlmClient(), _FakeMetrics()),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["backfill"])

    assert result.exit_code == 0

    db = Database(config.database.path)
    db.initialize()
    try:
        stats = db.get_stats()
    finally:
        db.close()

    assert stats["total_processed"] == 250


def test_backfill_resume_after_interruption_starts_from_saved_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Interrupted backfill should resume from persisted page token."""

    config = _config(tmp_path / "e2e-backfill-resume.db")
    pages = _pages(total=250, page_size=50)

    db = Database(config.database.path)
    db.initialize()
    try:
        db.upsert_backfill_state(
            BackfillState(
                id=None,
                last_page_token="p2",
                last_message_id="m100",
                status="interrupted",
                started_at="2026-04-15T00:00:00Z",
                completed_at="2026-04-15T00:05:00Z",
                total_processed=100,
                total_skipped=0,
            )
        )
        interrupted_state = db.get_latest_backfill_state()
    finally:
        db.close()

    assert interrupted_state is not None
    assert interrupted_state.status == "interrupted"
    assert interrupted_state.last_page_token == "p2"

    gmail_client_second = _FakeGmailClient(pages)
    monkeypatch.setattr("gmail_sorter.observability.configure_logging", lambda *_args: None)
    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)
    monkeypatch.setattr(
        "gmail_sorter.cli._build_engine",
        lambda _cfg, db: (_FakeEngine(db), gmail_client_second, _FakeLlmClient(), _FakeMetrics()),
    )

    runner = CliRunner()

    second_run = runner.invoke(main, ["backfill"])
    assert second_run.exit_code == 0
    assert gmail_client_second.calls[0] == "p2"
