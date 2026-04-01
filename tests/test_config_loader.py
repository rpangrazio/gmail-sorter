"""Tests for src/config_loader.py — 100% coverage."""

import pytest
import yaml

from src.config_loader import Category, Config, _require_fields, load_config

VALID_CAT = {
    "name": "work",
    "label": "AI-Sorted/Work",
    "description": "Work-related emails from colleagues and clients",
    "keywords": ["meeting", "project"],
}

VALID_CONFIG = {
    "google_project_id": "my-project",
    "pubsub_subscription": "projects/my-project/subscriptions/sub",
    "gmail_watch_topic": "projects/my-project/topics/topic",
    "categories": [VALID_CAT],
}


def write_yaml(tmp_path, data):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    return str(p)


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------

def test_load_config_happy_path(tmp_path):
    path = write_yaml(tmp_path, VALID_CONFIG)
    config = load_config(path)

    assert config.google_project_id == "my-project"
    assert config.pubsub_subscription == "projects/my-project/subscriptions/sub"
    assert config.gmail_watch_topic == "projects/my-project/topics/topic"
    assert len(config.categories) == 1

    cat = config.categories[0]
    assert cat.name == "work"
    assert cat.label == "AI-Sorted/Work"
    assert cat.keywords == ["meeting", "project"]

    # Defaults
    assert config.max_emails_per_poll == 10
    assert config.log_level == "INFO"
    assert config.dry_run is False
    assert config.ai_provider == "copilot"
    assert config.copilot_model == "gpt-4o"
    assert config.openai_model == "gpt-4o"
    assert config.state_backend == "json"


def test_load_config_custom_values(tmp_path):
    data = {
        **VALID_CONFIG,
        "max_emails_per_poll": 25,
        "log_level": "debug",
        "dry_run": True,
        "ai_provider": "openai",
        "copilot_model": "o3-mini",
        "openai_model": "gpt-4o-mini",
        "state_backend": "sqlite",
    }
    config = load_config(write_yaml(tmp_path, data))
    assert config.max_emails_per_poll == 25
    assert config.log_level == "DEBUG"
    assert config.dry_run is True
    assert config.ai_provider == "openai"
    assert config.copilot_model == "o3-mini"
    assert config.openai_model == "gpt-4o-mini"
    assert config.state_backend == "sqlite"


def test_load_config_no_keywords(tmp_path):
    cat = {k: v for k, v in VALID_CAT.items() if k != "keywords"}
    data = {**VALID_CONFIG, "categories": [cat]}
    config = load_config(write_yaml(tmp_path, data))
    assert config.categories[0].keywords == []


def test_load_config_multiple_categories(tmp_path):
    cat2 = {
        "name": "personal",
        "label": "AI-Sorted/Personal",
        "description": "Emails from friends and family members",
    }
    data = {**VALID_CONFIG, "categories": [VALID_CAT, cat2]}
    config = load_config(write_yaml(tmp_path, data))
    assert len(config.categories) == 2
    assert config.categories[1].name == "personal"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_load_config_file_not_found():
    with pytest.raises(FileNotFoundError, match="not found"):
        load_config("/nonexistent/path/config.yaml")


def test_load_config_not_a_dict(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("- this is a list")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(str(p))


def test_load_config_missing_google_project_id(tmp_path):
    data = {k: v for k, v in VALID_CONFIG.items() if k != "google_project_id"}
    with pytest.raises(ValueError, match="google_project_id"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_missing_pubsub_subscription(tmp_path):
    data = {k: v for k, v in VALID_CONFIG.items() if k != "pubsub_subscription"}
    with pytest.raises(ValueError, match="pubsub_subscription"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_missing_gmail_watch_topic(tmp_path):
    data = {k: v for k, v in VALID_CONFIG.items() if k != "gmail_watch_topic"}
    with pytest.raises(ValueError, match="gmail_watch_topic"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_missing_categories(tmp_path):
    data = {k: v for k, v in VALID_CONFIG.items() if k != "categories"}
    with pytest.raises(ValueError, match="categories"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_invalid_pubsub_subscription(tmp_path):
    data = {**VALID_CONFIG, "pubsub_subscription": "bad-path"}
    with pytest.raises(ValueError, match="pubsub_subscription"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_invalid_gmail_watch_topic(tmp_path):
    data = {**VALID_CONFIG, "gmail_watch_topic": "not-a-projects-path"}
    with pytest.raises(ValueError, match="gmail_watch_topic"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_empty_categories(tmp_path):
    data = {**VALID_CONFIG, "categories": []}
    with pytest.raises(ValueError, match="non-empty"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_categories_not_list(tmp_path):
    data = {**VALID_CONFIG, "categories": "not-a-list"}
    with pytest.raises(ValueError, match="non-empty"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_missing_category_name(tmp_path):
    cat = {k: v for k, v in VALID_CAT.items() if k != "name"}
    data = {**VALID_CONFIG, "categories": [cat]}
    with pytest.raises(ValueError, match="name"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_missing_category_label(tmp_path):
    cat = {k: v for k, v in VALID_CAT.items() if k != "label"}
    data = {**VALID_CONFIG, "categories": [cat]}
    with pytest.raises(ValueError, match="label"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_missing_category_description(tmp_path):
    cat = {k: v for k, v in VALID_CAT.items() if k != "description"}
    data = {**VALID_CONFIG, "categories": [cat]}
    with pytest.raises(ValueError, match="description"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_duplicate_category_name(tmp_path):
    cat2 = {**VALID_CAT, "label": "AI-Sorted/Work2"}
    data = {**VALID_CONFIG, "categories": [VALID_CAT, cat2]}
    with pytest.raises(ValueError, match="Duplicate"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_short_description(tmp_path):
    cat = {**VALID_CAT, "description": "Too short"}
    data = {**VALID_CONFIG, "categories": [cat]}
    with pytest.raises(ValueError, match="too short"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_invalid_ai_provider(tmp_path):
    data = {**VALID_CONFIG, "ai_provider": "gemini"}
    with pytest.raises(ValueError, match="ai_provider"):
        load_config(write_yaml(tmp_path, data))


def test_load_config_state_backend_postgres(tmp_path):
    data = {**VALID_CONFIG, "state_backend": "postgres"}
    config = load_config(write_yaml(tmp_path, data))
    assert config.state_backend == "postgres"


def test_load_config_invalid_state_backend(tmp_path):
    data = {**VALID_CONFIG, "state_backend": "redis"}
    with pytest.raises(ValueError, match="state_backend"):
        load_config(write_yaml(tmp_path, data))


# ---------------------------------------------------------------------------
# _require_fields
# ---------------------------------------------------------------------------

def test_require_fields_all_present():
    _require_fields({"a": 1, "b": 2}, ["a", "b"])  # Should not raise


def test_require_fields_missing_field():
    with pytest.raises(ValueError, match="required_key"):
        _require_fields({}, ["required_key"])


def test_require_fields_none_value():
    with pytest.raises(ValueError, match="none_field"):
        _require_fields({"none_field": None}, ["none_field"])


def test_require_fields_custom_context():
    with pytest.raises(ValueError, match="categories\\[0\\]"):
        _require_fields({}, ["missing"], context="categories[0]")
