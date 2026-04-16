"""Unit tests for CLI command wiring and global options."""

from __future__ import annotations

import asyncio
from types import ModuleType
from types import SimpleNamespace
import sys

from click.testing import CliRunner

from gmail_sorter.cli import _build_engine, _load_runtime_config, _run_service, main


def _fake_config() -> SimpleNamespace:
    """Return a lightweight config object used by CLI tests."""

    return SimpleNamespace(
        gmail=SimpleNamespace(),
        processing=SimpleNamespace(dry_run=False),
        logging=SimpleNamespace(level="INFO", log_prompts=False),
        database=SimpleNamespace(path="./gmail_sorter.db", retention_days=90),
        observability=SimpleNamespace(health_port=8080, metrics_port=9090),
    )


def test_validate_config_with_valid_config_exits_zero(monkeypatch) -> None:
    """`validate-config` succeeds when configuration loads cleanly."""

    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: _fake_config())
    runner = CliRunner()

    result = runner.invoke(main, ["validate-config"])

    assert result.exit_code == 0
    assert "Configuration is valid." in result.output


def test_validate_config_with_invalid_config_exits_one(monkeypatch) -> None:
    """`validate-config` exits non-zero when config validation fails."""

    def _raise(_path):
        raise SystemExit(1)

    monkeypatch.setattr("gmail_sorter.cli.load_config", _raise)
    runner = CliRunner()

    result = runner.invoke(main, ["validate-config"])

    assert result.exit_code == 1


def test_version_flag_prints_project_version() -> None:
    """`--version` reports the CLI package version."""

    runner = CliRunner()
    result = runner.invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "1.0.0" in result.output


def test_load_runtime_config_applies_global_overrides(monkeypatch) -> None:
    """Global CLI flags should override loaded configuration values."""

    config = _fake_config()
    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)

    options = SimpleNamespace(
        config_path="./config.yaml",
        dry_run=True,
        log_level="DEBUG",
    )
    loaded = _load_runtime_config(options)

    assert loaded.processing.dry_run is True
    assert loaded.logging.level == "DEBUG"


def test_auth_command_invokes_authenticator_and_logging(monkeypatch) -> None:
    """`auth` command should configure logging and run interactive auth."""

    config = _fake_config()
    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)

    called = {"configure": 0, "authenticate": 0}

    observability_module = ModuleType("gmail_sorter.observability")

    def _configure(level: str, log_prompts: bool) -> None:
        called["configure"] += 1
        assert level == "INFO"
        assert log_prompts is False

    observability_module.configure_logging = _configure
    monkeypatch.setitem(sys.modules, "gmail_sorter.observability", observability_module)

    auth_module = ModuleType("gmail_sorter.gmail.auth")

    class _Authenticator:
        def __init__(self, _gmail_config) -> None:
            pass

        def authenticate(self) -> None:
            called["authenticate"] += 1

    auth_module.GmailAuthenticator = _Authenticator
    monkeypatch.setitem(sys.modules, "gmail_sorter.gmail.auth", auth_module)

    runner = CliRunner()
    result = runner.invoke(main, ["auth"])

    assert result.exit_code == 0
    assert "Authentication completed." in result.output
    assert called == {"configure": 1, "authenticate": 1}


def test_stats_command_prints_expected_totals(monkeypatch) -> None:
    """`stats` command should print summary totals and category breakdown."""

    config = _fake_config()
    config.database = SimpleNamespace(path="./gmail_sorter.db", retention_days=90)
    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)

    class _FakeDatabase:
        def __init__(self, _path: str) -> None:
            pass

        def initialize(self) -> None:
            return None

        def get_stats(self):
            return {
                "total_processed": 10,
                "by_category": {"alerts": 7, "marketing": 3},
                "error_total": 2,
                "since": None,
                "until": None,
            }

        def enforce_retention(self, retention_days: int):
            assert retention_days == 90
            return {
                "classifications_deleted": 0,
                "dlq_deleted": 0,
                "retention_days": retention_days,
            }

        def close(self) -> None:
            return None

    monkeypatch.setattr("gmail_sorter.cli.Database", _FakeDatabase)

    runner = CliRunner()
    result = runner.invoke(main, ["stats"])

    assert result.exit_code == 0
    assert "Classification Statistics" in result.output
    assert "- Total processed: 10" in result.output
    assert "- Total errors: 2" in result.output
    assert "- Error rate: 16.67%" in result.output
    assert "- Date range: beginning to now" in result.output
    assert "alerts: 7" in result.output
    assert "marketing: 3" in result.output


def test_stats_command_supports_date_range_flags(monkeypatch) -> None:
    """`stats` command should pass parsed date range values to repository."""

    config = _fake_config()
    config.database = SimpleNamespace(path="./gmail_sorter.db", retention_days=90)
    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: config)

    observed = {"since": None, "until": None}

    class _FakeDatabase:
        def __init__(self, _path: str) -> None:
            pass

        def initialize(self) -> None:
            return None

        def enforce_retention(self, retention_days: int):
            assert retention_days == 90
            return {
                "classifications_deleted": 0,
                "dlq_deleted": 0,
                "retention_days": retention_days,
            }

        def get_stats(self, since=None, until=None):
            observed["since"] = since
            observed["until"] = until
            return {
                "total_processed": 1,
                "by_category": {"alerts": 1},
                "error_total": 0,
                "since": "2026-04-01T00:00:00Z",
                "until": "2026-04-30T00:00:00Z",
            }

        def close(self) -> None:
            return None

    monkeypatch.setattr("gmail_sorter.cli.Database", _FakeDatabase)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "stats",
            "--since",
            "2026-04-01",
            "--until",
            "2026-04-30",
        ],
    )

    assert result.exit_code == 0
    assert observed["since"] is not None
    assert observed["until"] is not None
    assert "- Date range: 2026-04-01T00:00:00Z to 2026-04-30T00:00:00Z" in result.output


def test_build_engine_wires_dependencies(monkeypatch) -> None:
    """Engine factory should wire all core components and dependency values."""

    class _GmailAuthenticator:
        def __init__(self, _gmail_config) -> None:
            pass

        def get_credentials(self):
            return "creds"

    class _GmailClient:
        def __init__(self, credentials, dry_run: bool = False) -> None:
            self.credentials = credentials
            self.dry_run = dry_run

    class _LabelManager:
        def __init__(self, _client) -> None:
            pass

        def ensure_all_labels(self, _categories):
            return {"marketing": "LBL-1"}

    class _LlmClient:
        def __init__(self, _llm_config, log_prompts: bool = False) -> None:
            self.log_prompts = log_prompts

    class _PromptBuilder:
        def __init__(self, _llm_config, _categories) -> None:
            pass

    class _IdempotencyChecker:
        def __init__(self, db, system_label_ids) -> None:
            self.db = db
            self.system_label_ids = system_label_ids

    class _MetricsCollector:
        pass

    class _ClassificationEngine:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    auth_module = ModuleType("gmail_sorter.gmail.auth")
    auth_module.GmailAuthenticator = _GmailAuthenticator
    monkeypatch.setitem(sys.modules, "gmail_sorter.gmail.auth", auth_module)

    client_module = ModuleType("gmail_sorter.gmail.client")
    client_module.GmailClient = _GmailClient
    monkeypatch.setitem(sys.modules, "gmail_sorter.gmail.client", client_module)

    labels_module = ModuleType("gmail_sorter.gmail.labels")
    labels_module.LabelManager = _LabelManager
    monkeypatch.setitem(sys.modules, "gmail_sorter.gmail.labels", labels_module)

    llm_module = ModuleType("gmail_sorter.llm.client")
    llm_module.LlmClient = _LlmClient
    monkeypatch.setitem(sys.modules, "gmail_sorter.llm.client", llm_module)

    prompt_module = ModuleType("gmail_sorter.processor.prompt_builder")
    prompt_module.PromptBuilder = _PromptBuilder
    monkeypatch.setitem(sys.modules, "gmail_sorter.processor.prompt_builder", prompt_module)

    idem_module = ModuleType("gmail_sorter.classifier.idempotency")
    idem_module.IdempotencyChecker = _IdempotencyChecker
    monkeypatch.setitem(sys.modules, "gmail_sorter.classifier.idempotency", idem_module)

    metrics_module = ModuleType("gmail_sorter.observability.metrics")
    metrics_module.MetricsCollector = _MetricsCollector
    monkeypatch.setitem(sys.modules, "gmail_sorter.observability.metrics", metrics_module)

    engine_module = ModuleType("gmail_sorter.classifier.engine")
    engine_module.ClassificationEngine = _ClassificationEngine
    monkeypatch.setitem(sys.modules, "gmail_sorter.classifier.engine", engine_module)

    config = SimpleNamespace(
        gmail=SimpleNamespace(),
        processing=SimpleNamespace(dry_run=True),
        llm=SimpleNamespace(),
        logging=SimpleNamespace(log_prompts=True),
        categories=[SimpleNamespace(name="marketing", label="AutoSort/Marketing")],
    )
    fake_db = object()

    engine, gmail_client, llm_client, metrics = _build_engine(config, fake_db)

    assert isinstance(gmail_client, _GmailClient)
    assert gmail_client.credentials == "creds"
    assert gmail_client.dry_run is True
    assert isinstance(llm_client, _LlmClient)
    assert llm_client.log_prompts is True
    assert isinstance(metrics, _MetricsCollector)
    assert isinstance(engine, _ClassificationEngine)
    assert engine.kwargs["db"] is fake_db
    assert engine.kwargs["label_map"] == {"marketing": "LBL-1"}


def test_run_service_uses_configured_observability_ports(monkeypatch) -> None:
    """Service runtime should start metrics/health servers on configured ports."""

    observed = {"metrics_port": None, "health_port": None}

    class _FakeMetrics:
        def start_http_server(self, port: int = 9090) -> None:
            observed["metrics_port"] = port

    class _FakeLlmClient:
        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        "gmail_sorter.cli._build_engine",
        lambda config, db: (SimpleNamespace(), SimpleNamespace(), _FakeLlmClient(), _FakeMetrics()),
    )

    observability_module = ModuleType("gmail_sorter.observability")

    class _HealthServer:
        def __init__(self, port: int = 8080) -> None:
            observed["health_port"] = port

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def set_healthy(self, last_message_at: str | None = None) -> None:
            _ = last_message_at

    observability_module.HealthServer = _HealthServer
    monkeypatch.setitem(sys.modules, "gmail_sorter.observability", observability_module)

    pubsub_listener_module = ModuleType("gmail_sorter.pubsub.listener")

    class _PubSubListener:
        def __init__(self, config, engine, metrics) -> None:
            _ = (config, engine, metrics)

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    pubsub_listener_module.PubSubListener = _PubSubListener
    monkeypatch.setitem(sys.modules, "gmail_sorter.pubsub.listener", pubsub_listener_module)

    pubsub_watcher_module = ModuleType("gmail_sorter.pubsub.watcher")

    class _GmailWatcher:
        def __init__(self, gmail_client, config) -> None:
            _ = (gmail_client, config)

        def register(self) -> dict:
            return {}

        def schedule_renewal(self) -> None:
            return None

        def stop(self) -> None:
            return None

    pubsub_watcher_module.GmailWatcher = _GmailWatcher
    monkeypatch.setitem(sys.modules, "gmail_sorter.pubsub.watcher", pubsub_watcher_module)

    backfill_module = ModuleType("gmail_sorter.backfill.engine")

    class _BackfillEngine:
        def __init__(self, **kwargs) -> None:
            _ = kwargs

        async def run(self) -> None:
            return None

    backfill_module.BackfillEngine = _BackfillEngine
    monkeypatch.setitem(sys.modules, "gmail_sorter.backfill.engine", backfill_module)

    config = SimpleNamespace(
        database=SimpleNamespace(path=":memory:", retention_days=90),
        observability=SimpleNamespace(health_port=18080, metrics_port=19090),
        pubsub=SimpleNamespace(),
    )

    asyncio.run(_run_service(config, run_backfill=False))

    assert observed["metrics_port"] == 19090
    assert observed["health_port"] == 18080
