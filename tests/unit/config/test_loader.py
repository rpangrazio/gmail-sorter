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
  provider: "github_copilot"
  model: "gpt-4o"
  api_key_env: "GITHUB_COPILOT_API_KEY"
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
  provider: "github_copilot"
  model: "gpt-4o"
  api_key_env: "GITHUB_COPILOT_API_KEY"
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
