"""Unit tests for PRD-aligned error taxonomy helpers."""

from __future__ import annotations

from gmail_sorter.observability.error_taxonomy import classify_exception, normalize_error_type


def test_normalize_error_type_accepts_required_values() -> None:
    """Known taxonomy labels should pass through unchanged."""

    assert normalize_error_type("auth_error") == "auth_error"
    assert normalize_error_type("api_error") == "api_error"
    assert normalize_error_type("llm_error") == "llm_error"
    assert normalize_error_type("config_error") == "config_error"
    assert normalize_error_type("pubsub_error") == "pubsub_error"


def test_normalize_error_type_falls_back_for_unknown_values() -> None:
    """Unknown labels should map to api_error for metric/log consistency."""

    assert normalize_error_type("") == "api_error"
    assert normalize_error_type(None) == "api_error"
    assert normalize_error_type("db_error") == "api_error"


def test_classify_exception_returns_required_taxonomy_values() -> None:
    """Exception mapping should cover auth, pubsub, llm, config, and fallback."""

    class OAuthTokenError(Exception):
        pass

    class PubSubProcessingError(Exception):
        pass

    assert classify_exception(OAuthTokenError("oauth failed")) == "auth_error"
    assert classify_exception(PubSubProcessingError("pubsub failed")) == "pubsub_error"
    assert classify_exception(TimeoutError("request timeout")) == "llm_error"
    assert classify_exception(SystemExit(1)) == "config_error"
    assert classify_exception(RuntimeError("unexpected")) == "api_error"
