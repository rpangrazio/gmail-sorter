"""Unit tests for configuration model validation."""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from gmail_sorter.config.models import AppConfig


@pytest.fixture
def valid_config_dict() -> dict:
    """Return a valid config payload mirroring the default config file."""

    return {
        "gmail": {
            "credentials_path": "./credentials.json",
            "token_path": "./token.json",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.labels",
                "https://www.googleapis.com/auth/gmail.modify",
            ],
        },
        "pubsub": {
            "project_id": "my-gcp-project-id",
            "topic": "gmail-notifications",
            "subscription": "gmail-sorter-subscription",
            "mode": "pull",
        },
        "llm": {
            "provider": "github_copilot",
            "model": "gpt-4o",
            "api_key_env": "GITHUB_COPILOT_API_KEY",
            "timeout_seconds": 30,
            "max_retries": 3,
            "system_prompt": "You are an expert email classification assistant.",
            "prompt_template": "./prompts/classify_email.j2",
        },
        "classification": {
            "confidence_threshold": 0.7,
            "fallback_category": "uncategorized",
            "multi_label": False,
        },
        "categories": [
            {
                "name": "marketing",
                "label": "AutoSort/Marketing",
                "description": "Promotional content.",
            },
            {
                "name": "billing",
                "label": "AutoSort/Billing",
                "description": "Invoices and payment notices.",
            },
        ],
        "processing": {
            "body_max_length": 4096,
            "batch_size": 50,
            "backfill_concurrency": 5,
            "archive_after_label": False,
            "dry_run": False,
        },
        "logging": {"level": "INFO", "log_prompts": False},
        "database": {"path": "./gmail_sorter.db"},
    }


def test_valid_config_loads_without_error(valid_config_dict: dict) -> None:
    """A valid config payload should pass model validation."""

    config = AppConfig.model_validate(valid_config_dict)
    assert config.gmail.credentials_path == "./credentials.json"
    assert config.classification.allowlist == []
    assert config.classification.blocklist == []
    assert config.processing.backfill_progress_interval == 100
    assert config.pubsub.push_endpoint is None
    assert config.pubsub.push_port == 8081
    assert config.database.retention_days == 90
    assert config.observability.health_port == 8080
    assert config.observability.metrics_port == 9090
    assert config.alerts.webhook_url is None


def test_duplicate_category_name_raises_value_error(valid_config_dict: dict) -> None:
    """Duplicate category names should trigger model-level validation errors."""

    payload = copy.deepcopy(valid_config_dict)
    payload["categories"].append(
        {
            "name": "marketing",
            "label": "AutoSort/Marketing-2",
            "description": "Another category.",
        }
    )

    with pytest.raises(ValidationError, match="Duplicate category name found"):
        AppConfig.model_validate(payload)


def test_duplicate_category_label_raises_value_error(valid_config_dict: dict) -> None:
    """Duplicate category labels should trigger model-level validation errors."""

    payload = copy.deepcopy(valid_config_dict)
    payload["categories"].append(
        {
            "name": "marketing_2",
            "label": "AutoSort/Marketing",
            "description": "Another category.",
        }
    )

    with pytest.raises(ValidationError, match="Conflicting category label found"):
        AppConfig.model_validate(payload)


def test_missing_required_field_raises_validation_error(valid_config_dict: dict) -> None:
    """Missing required fields should fail schema validation."""

    payload = copy.deepcopy(valid_config_dict)
    del payload["gmail"]["credentials_path"]

    with pytest.raises(ValidationError):
        AppConfig.model_validate(payload)


def test_confidence_threshold_outside_range_raises_validation_error(
    valid_config_dict: dict,
) -> None:
    """The confidence threshold must remain in the inclusive [0.0, 1.0] range."""

    payload = copy.deepcopy(valid_config_dict)
    payload["classification"]["confidence_threshold"] = 1.1

    with pytest.raises(ValidationError):
        AppConfig.model_validate(payload)


def test_negative_backfill_progress_interval_raises_validation_error(
    valid_config_dict: dict,
) -> None:
    """Backfill progress interval must be a positive integer."""

    payload = copy.deepcopy(valid_config_dict)
    payload["processing"]["backfill_progress_interval"] = 0

    with pytest.raises(ValidationError):
        AppConfig.model_validate(payload)


def test_out_of_range_ports_raise_validation_error(valid_config_dict: dict) -> None:
    """Port fields must be in the valid TCP range."""

    payload = copy.deepcopy(valid_config_dict)
    payload["pubsub"]["push_port"] = 70000

    with pytest.raises(ValidationError):
        AppConfig.model_validate(payload)


def test_negative_retention_days_raises_validation_error(
    valid_config_dict: dict,
) -> None:
    """Retention period must be at least one day."""

    payload = copy.deepcopy(valid_config_dict)
    payload["database"]["retention_days"] = -1

    with pytest.raises(ValidationError):
        AppConfig.model_validate(payload)
