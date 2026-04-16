"""Unit tests for LLM response parsing behavior."""

from __future__ import annotations

import pytest

from gmail_sorter.llm.response_parser import LlmParseError, parse_response


def test_parse_response_valid_payload() -> None:
    """A valid JSON payload should parse into a typed LLM response."""

    raw = '{"category": "marketing", "confidence": 0.91, "reasoning": "Promo content."}'
    parsed = parse_response(
        raw_content=raw,
        valid_categories=["marketing", "alerts"],
        fallback="uncategorized",
        threshold=0.7,
    )

    assert parsed.category == "marketing"
    assert parsed.confidence == 0.91
    assert parsed.reasoning == "Promo content."
    assert parsed.raw == raw


def test_parse_response_unknown_category_falls_back() -> None:
    """Unknown categories should route to the configured fallback."""

    raw = '{"category": "unknown", "confidence": 0.95, "reasoning": "Unsure."}'
    parsed = parse_response(
        raw_content=raw,
        valid_categories=["marketing", "alerts"],
        fallback="uncategorized",
        threshold=0.7,
    )

    assert parsed.category == "uncategorized"
    assert parsed.confidence == 0.95


def test_parse_response_low_confidence_falls_back() -> None:
    """Classifications below threshold should route to fallback category."""

    raw = '{"category": "marketing", "confidence": 0.2, "reasoning": "Low confidence."}'
    parsed = parse_response(
        raw_content=raw,
        valid_categories=["marketing"],
        fallback="uncategorized",
        threshold=0.7,
    )

    assert parsed.category == "uncategorized"
    assert parsed.confidence == 0.2


def test_parse_response_clamps_confidence() -> None:
    """Confidence values should be clamped to the [0.0, 1.0] range."""

    raw = '{"category": "marketing", "confidence": 3.2, "reasoning": "Too high."}'
    parsed = parse_response(
        raw_content=raw,
        valid_categories=["marketing"],
        fallback="uncategorized",
        threshold=0.0,
    )

    assert parsed.category == "marketing"
    assert parsed.confidence == 1.0


def test_parse_response_extracts_json_substring() -> None:
    """Parser should recover JSON object embedded in surrounding text."""

    raw = 'Result:\n```json\n{"category":"alerts","confidence":0.77,"reasoning":"System event."}\n```'
    parsed = parse_response(
        raw_content=raw,
        valid_categories=["alerts"],
        fallback="uncategorized",
        threshold=0.7,
    )

    assert parsed.category == "alerts"
    assert parsed.confidence == 0.77


def test_parse_response_raises_on_non_json_content() -> None:
    """Completely invalid model output should raise parse error."""

    with pytest.raises(LlmParseError):
        parse_response(
            raw_content="not json at all",
            valid_categories=["marketing"],
            fallback="uncategorized",
            threshold=0.7,
        )


def test_parse_response_multi_label_enabled_parses_categories_list() -> None:
    """Multi-label mode should parse and validate all returned categories."""

    raw = (
        '{"categories":[{"category":"alerts","confidence":0.9,'
        '"reasoning":"Alert."},{"category":"unknown","confidence":0.8,'
        '"reasoning":"Unknown."}]}'
    )
    parsed = parse_response(
        raw_content=raw,
        valid_categories=["alerts", "marketing"],
        fallback="uncategorized",
        threshold=0.7,
        multi_label=True,
    )

    assert parsed.category == "alerts"
    assert parsed.categories == ["alerts", "uncategorized"]
    assert parsed.confidence == 0.9


def test_parse_response_multi_label_disabled_uses_single_category_contract() -> None:
    """Single-label mode should ignore categories list payloads."""

    raw = '{"categories":[{"category":"alerts","confidence":0.9}]}'
    parsed = parse_response(
        raw_content=raw,
        valid_categories=["alerts"],
        fallback="uncategorized",
        threshold=0.7,
        multi_label=False,
    )

    assert parsed.category == "uncategorized"
    assert parsed.categories == ["uncategorized"]
