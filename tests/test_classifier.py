"""Tests for src/classifier.py — 100% coverage."""

from unittest.mock import MagicMock, patch

import pytest

from src.classifier import (
    BaseClassifier,
    CopilotClassifier,
    OpenAIClassifier,
    _build_system_prompt,
    _format_email_for_prompt,
    create_classifier,
)
from src.config_loader import Category, Config


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_config(ai_provider: str = "copilot") -> Config:
    return Config(
        google_project_id="proj",
        pubsub_subscription="projects/proj/subscriptions/sub",
        gmail_watch_topic="projects/proj/topics/topic",
        categories=[
            Category(
                name="work",
                label="AI-Sorted/Work",
                description="Work-related emails",
                keywords=["meeting"],
            ),
            Category(
                name="personal",
                label="AI-Sorted/Personal",
                description="Personal emails",
                keywords=[],
            ),
        ],
        ai_provider=ai_provider,
    )


EMAIL_DATA = {
    "subject": "Team Meeting Tomorrow",
    "from_": "boss@company.com",
    "to": "me@example.com",
    "date": "2024-01-01",
    "snippet": "Let's meet tomorrow",
    "body": "Hi, let's have a meeting tomorrow at 10am.",
}


class ConcreteClassifier(BaseClassifier):
    """Minimal concrete subclass for testing the abstract base helpers."""

    @property
    def provider_name(self) -> str:
        return "test"

    def classify(self, email_data):
        return self._parse_category("work")


# ---------------------------------------------------------------------------
# BaseClassifier._parse_category
# ---------------------------------------------------------------------------

def test_parse_category_exact_match():
    clf = ConcreteClassifier(make_config())
    assert clf._parse_category("work") == "work"
    assert clf._parse_category("personal") == "personal"


def test_parse_category_none_variants():
    clf = ConcreteClassifier(make_config())
    for variant in ("none", "n/a", "unknown", "other", "no match"):
        assert clf._parse_category(variant) is None


def test_parse_category_strips_punctuation():
    clf = ConcreteClassifier(make_config())
    assert clf._parse_category("work.") == "work"
    assert clf._parse_category("work!") == "work"
    assert clf._parse_category("`work`") == "work"


def test_parse_category_substring_match():
    clf = ConcreteClassifier(make_config())
    assert clf._parse_category("category: work") == "work"
    assert clf._parse_category("the answer is personal here") == "personal"


def test_parse_category_unrecognized_returns_none():
    clf = ConcreteClassifier(make_config())
    assert clf._parse_category("gibberish_xyz_qqq") is None


# ---------------------------------------------------------------------------
# BaseClassifier._log_result
# ---------------------------------------------------------------------------

def test_log_result_with_category(caplog):
    import logging
    clf = ConcreteClassifier(make_config())
    with caplog.at_level(logging.INFO, logger="src.classifier"):
        clf._log_result("work", "Test Subject")
    assert "work" in caplog.text


def test_log_result_none_category(caplog):
    import logging
    clf = ConcreteClassifier(make_config())
    with caplog.at_level(logging.INFO, logger="src.classifier"):
        clf._log_result(None, "Test Subject")
    assert "No category" in caplog.text


# ---------------------------------------------------------------------------
# CopilotClassifier
# ---------------------------------------------------------------------------

def _make_copilot_mock(response_text):
    """Return (mock_module, mock_client) configured for CopilotClassifier."""
    mock_module = MagicMock()
    mock_client = MagicMock()
    mock_module.OpenAI.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices[0].message.content = response_text
    mock_client.chat.completions.create.return_value = mock_response
    return mock_module, mock_client


def test_copilot_classifier_init():
    mock_module = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = CopilotClassifier(github_token="ghp_test", config=make_config())
    mock_module.OpenAI.assert_called_with(
        api_key="ghp_test",
        base_url="https://api.githubcopilot.com",
    )
    assert clf.provider_name == "copilot"


def test_copilot_classifier_classify_match():
    mock_module, _ = _make_copilot_mock("work")
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = CopilotClassifier(github_token="ghp_test", config=make_config())
        result = clf.classify(EMAIL_DATA)
    assert result == "work"


def test_copilot_classifier_classify_none():
    mock_module, _ = _make_copilot_mock("none")
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = CopilotClassifier(github_token="ghp_test", config=make_config())
        result = clf.classify(EMAIL_DATA)
    assert result is None


def test_copilot_classifier_classify_none_content():
    """message.content is None → empty string → unrecognized → None."""
    mock_module, _ = _make_copilot_mock(None)
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = CopilotClassifier(github_token="ghp_test", config=make_config())
        result = clf.classify(EMAIL_DATA)
    assert result is None


def test_copilot_classifier_import_error():
    with patch.dict("sys.modules", {"openai": None}):
        with pytest.raises(ImportError, match="openai"):
            CopilotClassifier(github_token="ghp_test", config=make_config())


def test_copilot_classifier_custom_model():
    mock_module = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = CopilotClassifier(github_token="ghp_test", config=make_config(), model="o3-mini")
    assert clf._model == "o3-mini"


# ---------------------------------------------------------------------------
# OpenAIClassifier
# ---------------------------------------------------------------------------

def _make_openai_module(response_text):
    mock_module = MagicMock()
    mock_client = MagicMock()
    mock_module.OpenAI.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices[0].message.content = response_text
    mock_client.chat.completions.create.return_value = mock_response
    return mock_module, mock_client


def test_openai_classifier_init_no_base_url():
    mock_module = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = OpenAIClassifier(api_key="oai-key", config=make_config("openai"))
    mock_module.OpenAI.assert_called_with(api_key="oai-key")
    assert clf.provider_name == "openai"


def test_openai_classifier_init_with_base_url():
    mock_module = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = OpenAIClassifier(
            api_key="oai-key",
            config=make_config("openai"),
            base_url="https://custom.api.com/v1",
        )
    mock_module.OpenAI.assert_called_with(api_key="oai-key", base_url="https://custom.api.com/v1")


def test_openai_classifier_import_error():
    with patch.dict("sys.modules", {"openai": None}):
        with pytest.raises(ImportError, match="openai"):
            OpenAIClassifier(api_key="key", config=make_config("openai"))


def test_openai_classifier_classify_match():
    mock_module, _ = _make_openai_module("personal")
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = OpenAIClassifier(api_key="key", config=make_config("openai"))
        result = clf.classify(EMAIL_DATA)
    assert result == "personal"


def test_openai_classifier_classify_none_content():
    """message.content is None → empty string → unrecognized → None."""
    mock_module, _ = _make_openai_module(None)
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = OpenAIClassifier(api_key="key", config=make_config("openai"))
        result = clf.classify(EMAIL_DATA)
    assert result is None


def test_openai_classifier_custom_model():
    mock_module = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = OpenAIClassifier(api_key="key", config=make_config("openai"), model="gpt-4o-mini")
    assert clf._model == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# create_classifier factory
# ---------------------------------------------------------------------------

def test_create_classifier_copilot():
    mock_module = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = create_classifier(make_config("copilot"), github_token="ghp_test")
    assert isinstance(clf, CopilotClassifier)


def test_create_classifier_openai():
    mock_module = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = create_classifier(make_config("openai"), openai_api_key="key")
    assert isinstance(clf, OpenAIClassifier)


def test_create_classifier_openai_with_base_url():
    mock_module = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = create_classifier(
            make_config("openai"),
            openai_api_key="key",
            openai_base_url="https://custom.com/v1",
        )
    assert isinstance(clf, OpenAIClassifier)


def test_create_classifier_openai_empty_base_url():
    """openai_base_url='' is treated as None (no custom endpoint)."""
    mock_module = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_module}):
        clf = create_classifier(
            make_config("openai"),
            openai_api_key="key",
            openai_base_url="",
        )
    assert isinstance(clf, OpenAIClassifier)


def test_create_classifier_missing_github_token():
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        create_classifier(make_config("copilot"), github_token="")


def test_create_classifier_missing_openai_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_classifier(make_config("openai"), openai_api_key="")


def test_create_classifier_unknown_provider():
    config = make_config("copilot")
    config.ai_provider = "gemini"
    with pytest.raises(ValueError, match="Unknown"):
        create_classifier(config, github_token="key")


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def test_build_system_prompt_with_keywords():
    cats = [Category(name="work", label="L", description="Work emails", keywords=["meeting", "deadline"])]
    prompt = _build_system_prompt(cats)
    assert "work" in prompt
    assert "meeting" in prompt
    assert "deadline" in prompt


def test_build_system_prompt_no_keywords():
    cats = [Category(name="personal", label="L", description="Personal emails")]
    prompt = _build_system_prompt(cats)
    assert "personal" in prompt
    assert "hint keywords" not in prompt


def test_build_system_prompt_multiple_categories():
    cats = [
        Category(name="work", label="L1", description="Work emails", keywords=["meeting"]),
        Category(name="personal", label="L2", description="Personal emails"),
    ]
    prompt = _build_system_prompt(cats)
    assert "work" in prompt
    assert "personal" in prompt


def test_format_email_for_prompt_all_fields():
    result = _format_email_for_prompt(EMAIL_DATA)
    assert "Team Meeting Tomorrow" in result
    assert "boss@company.com" in result
    assert "me@example.com" in result
    assert "2024-01-01" in result


def test_format_email_for_prompt_uses_snippet_when_no_body():
    email = {"subject": "S", "from_": "a@b.com", "snippet": "Snippet text"}
    result = _format_email_for_prompt(email)
    assert "Snippet text" in result


def test_format_email_for_prompt_body_truncated_at_1500():
    email = {**EMAIL_DATA, "body": "x" * 3000}
    result = _format_email_for_prompt(email)
    assert "x" * 3000 not in result
    assert "x" * 1500 in result
