"""Unit tests for configuration file loading behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from gmail_sorter.config.loader import load_config


def test_load_config_returns_app_config_for_valid_yaml(tmp_path: Path) -> None:
    """Loader should parse valid YAML and return typed app config."""

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
gmail:
  credentials_path: "./credentials.json"
  token_path: "./token.json"
  scopes:
    - "https://www.googleapis.com/auth/gmail.readonly"
    - "https://www.googleapis.com/auth/gmail.labels"
    - "https://www.googleapis.com/auth/gmail.modify"
pubsub:
  project_id: "project"
  topic: "topic"
  subscription: "subscription"
  mode: "pull"
llm:
  provider: "openai_compatible"
  model: "gpt-4o"
  api_key_env: "OPENAI_API_KEY"
  timeout_seconds: 30
  max_retries: 3
  system_prompt: "system"
  prompt_template: "./prompts/classify_email.j2"
classification:
  confidence_threshold: 0.7
  fallback_category: "uncategorized"
  multi_label: false
categories:
  - name: "alerts"
    label: "AutoSort/Alerts"
    description: "System notifications"
processing:
  body_max_length: 4096
  batch_size: 50
  backfill_concurrency: 5
  archive_after_label: false
  dry_run: false
logging:
  level: "INFO"
  log_prompts: false
database:
  path: "./gmail_sorter.db"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)
    assert config.gmail.credentials_path == "./credentials.json"
    assert config.categories[0].name == "alerts"
    assert config.processing.backfill_progress_interval == 100
    assert config.pubsub.push_port == 8081
    assert config.pubsub.auth_mode == "default"
    assert config.pubsub.credentials_path is None
    assert config.database.retention_days == 90
    assert config.observability.health_port == 8080
    assert config.observability.metrics_port == 9090
    assert config.alerts.webhook_url is None


def test_load_config_accepts_pubsub_service_account_fields(tmp_path: Path) -> None:
    """Loader should parse explicit service-account auth settings."""

    config_path = tmp_path / "config_service_account.yaml"
    config_path.write_text(
        """
gmail:
  credentials_path: "./credentials.json"
  token_path: "./token.json"
  scopes:
    - "https://www.googleapis.com/auth/gmail.readonly"
    - "https://www.googleapis.com/auth/gmail.labels"
    - "https://www.googleapis.com/auth/gmail.modify"
pubsub:
  project_id: "project"
  topic: "topic"
  subscription: "subscription"
  mode: "pull"
  auth_mode: "service_account"
  credentials_path: "./service-account.json"
llm:
  provider: "openai_compatible"
  model: "gpt-4o"
  api_key_env: "OPENAI_API_KEY"
  timeout_seconds: 30
  max_retries: 3
  system_prompt: "system"
  prompt_template: "./prompts/classify_email.j2"
classification:
  confidence_threshold: 0.7
  fallback_category: "uncategorized"
  multi_label: false
categories:
  - name: "alerts"
    label: "AutoSort/Alerts"
    description: "System notifications"
processing:
  body_max_length: 4096
  batch_size: 50
  backfill_concurrency: 5
  archive_after_label: false
  dry_run: false
logging:
  level: "INFO"
  log_prompts: false
database:
  path: "./gmail_sorter.db"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)
    assert config.pubsub.auth_mode == "service_account"
    assert config.pubsub.credentials_path == "./service-account.json"


def test_load_config_accepts_alerts_webhook_url(tmp_path: Path) -> None:
    """Loader should parse optional alerts webhook URL from config."""

    config_path = tmp_path / "config_with_webhook.yaml"
    config_path.write_text(
        """
gmail:
  credentials_path: "./credentials.json"
  token_path: "./token.json"
  scopes:
    - "https://www.googleapis.com/auth/gmail.readonly"
    - "https://www.googleapis.com/auth/gmail.labels"
    - "https://www.googleapis.com/auth/gmail.modify"
pubsub:
  project_id: "project"
  topic: "topic"
  subscription: "subscription"
  mode: "pull"
llm:
  provider: "openai_compatible"
  model: "gpt-4o"
  api_key_env: "OPENAI_API_KEY"
  timeout_seconds: 30
  max_retries: 3
  system_prompt: "system"
  prompt_template: "./prompts/classify_email.j2"
classification:
  confidence_threshold: 0.7
  fallback_category: "uncategorized"
  multi_label: false
categories:
  - name: "alerts"
    label: "AutoSort/Alerts"
    description: "System notifications"
processing:
  body_max_length: 4096
  batch_size: 50
  backfill_concurrency: 5
  archive_after_label: false
  dry_run: false
logging:
  level: "INFO"
  log_prompts: false
database:
  path: "./gmail_sorter.db"
alerts:
  webhook_url: "https://hooks.example.test/critical"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)
    assert config.alerts.webhook_url == "https://hooks.example.test/critical"


def test_load_config_exits_on_yaml_parse_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Loader should exit with parse error details for invalid YAML."""

    config_path = tmp_path / "broken.yaml"
    config_path.write_text("gmail: [", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        load_config(config_path)

    assert exc.value.code == 1
    assert "Configuration YAML parse error:" in capsys.readouterr().err


def test_load_config_exits_on_validation_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Loader should print field path and message for schema errors."""

    config_path = tmp_path / "invalid.yaml"
    config_path.write_text(
        """
gmail:
  token_path: "./token.json"
  scopes: []
pubsub:
  project_id: "project"
  topic: "topic"
  subscription: "subscription"
  mode: "pull"
llm:
  provider: "openai_compatible"
  model: "gpt-4o"
  api_key_env: "OPENAI_API_KEY"
  timeout_seconds: 30
  max_retries: 3
  system_prompt: "system"
  prompt_template: "./prompts/classify_email.j2"
classification:
  confidence_threshold: 0.7
  fallback_category: "uncategorized"
  multi_label: false
categories:
  - name: "alerts"
    label: "AutoSort/Alerts"
    description: "System notifications"
processing:
  body_max_length: 4096
  batch_size: 50
  backfill_concurrency: 5
  archive_after_label: false
  dry_run: false
logging:
  level: "INFO"
  log_prompts: false
database:
  path: "./gmail_sorter.db"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        load_config(config_path)

    stderr = capsys.readouterr().err
    assert exc.value.code == 1
    assert "gmail.credentials_path" in stderr


@pytest.mark.parametrize(
    ("snippet", "expected_path"),
    [
        ("processing:\n  backfill_progress_interval: 0", "processing.backfill_progress_interval"),
        ("database:\n  retention_days: 0", "database.retention_days"),
        ("pubsub:\n  push_port: 70000", "pubsub.push_port"),
        ("observability:\n  health_port: 0", "observability.health_port"),
        (
            "pubsub:\n  auth_mode: \"service_account\"",
            "pubsub",
        ),
    ],
)
def test_load_config_exits_on_invalid_new_runtime_controls(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    snippet: str,
    expected_path: str,
) -> None:
    """Loader should reject invalid values for newly added runtime controls."""

    config_path = tmp_path / "invalid_runtime_controls.yaml"
    config_path.write_text(
        f"""
gmail:
  credentials_path: "./credentials.json"
  token_path: "./token.json"
  scopes:
    - "https://www.googleapis.com/auth/gmail.readonly"
    - "https://www.googleapis.com/auth/gmail.labels"
    - "https://www.googleapis.com/auth/gmail.modify"
pubsub:
  project_id: "project"
  topic: "topic"
  subscription: "subscription"
  mode: "pull"
llm:
  provider: "openai_compatible"
  model: "gpt-4o"
  api_key_env: "OPENAI_API_KEY"
  timeout_seconds: 30
  max_retries: 3
  system_prompt: "system"
  prompt_template: "./prompts/classify_email.j2"
classification:
  confidence_threshold: 0.7
  fallback_category: "uncategorized"
  multi_label: false
categories:
  - name: "alerts"
    label: "AutoSort/Alerts"
    description: "System notifications"
processing:
  body_max_length: 4096
  batch_size: 50
  backfill_concurrency: 5
  archive_after_label: false
  dry_run: false
logging:
  level: "INFO"
  log_prompts: false
database:
  path: "./gmail_sorter.db"
observability:
  health_port: 8080
  metrics_port: 9090
{snippet}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        load_config(config_path)

    stderr = capsys.readouterr().err
    assert exc.value.code == 1
    assert expected_path in stderr
