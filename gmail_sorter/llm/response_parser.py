"""LLM response parsing utilities.

This module normalizes raw model output into a typed response object and
applies category and confidence guardrails required by the classification
pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


class LlmParseError(ValueError):
    """Raised when an LLM response cannot be parsed as valid JSON."""


@dataclass(slots=True)
class LlmResponse:
    """Normalized LLM classification response."""

    category: str
    confidence: float
    reasoning: str
    raw: str
    categories: list[str] = field(default_factory=list)


def _extract_json_payload(raw_content: str) -> dict[str, Any]:
    """Decode JSON from model output, with a first-object regex fallback."""

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*?\}", raw_content, flags=re.DOTALL)
        if not match:
            raise LlmParseError("Could not find a JSON object in model response.")

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LlmParseError("Model response contained malformed JSON.") from exc

    if not isinstance(parsed, dict):
        raise LlmParseError("Model response JSON must be an object.")

    return parsed


def parse_response(
    raw_content: str,
    valid_categories: list[str],
    fallback: str,
    threshold: float,
    multi_label: bool = False,
) -> LlmResponse:
    """Parse and validate a model response against classification constraints."""

    payload = _extract_json_payload(raw_content)

    if multi_label:
        return _parse_multi_label_response(
            payload=payload,
            raw_content=raw_content,
            valid_categories=valid_categories,
            fallback=fallback,
            threshold=threshold,
        )

    category = str(payload.get("category", fallback)).strip() or fallback

    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reasoning = str(payload.get("reasoning", "")).strip()

    if valid_categories and category not in valid_categories:
        category = fallback
    if confidence < threshold:
        category = fallback

    return LlmResponse(
        category=category,
        confidence=confidence,
        reasoning=reasoning,
        raw=raw_content,
        categories=[category],
    )


def _parse_multi_label_response(
    payload: dict[str, Any],
    raw_content: str,
    valid_categories: list[str],
    fallback: str,
    threshold: float,
) -> LlmResponse:
    """Parse multi-label response payloads into normalized category outputs."""

    items_raw = payload.get("categories")
    if isinstance(items_raw, list) and items_raw:
        candidates = items_raw
    else:
        candidates = [payload]

    resolved_categories: list[str] = []
    confidence_values: list[float] = []
    reason_fragments: list[str] = []

    for item in candidates:
        if not isinstance(item, dict):
            continue

        category = str(item.get("category", fallback)).strip() or fallback
        confidence_raw = item.get("confidence", payload.get("confidence", 0.0))
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        if valid_categories and category not in valid_categories:
            category = fallback
        if confidence < threshold:
            category = fallback

        if category not in resolved_categories:
            resolved_categories.append(category)

        confidence_values.append(confidence)

        reasoning = str(item.get("reasoning", payload.get("reasoning", ""))).strip()
        if reasoning and reasoning not in reason_fragments:
            reason_fragments.append(reasoning)

    if not resolved_categories:
        resolved_categories = [fallback]

    primary_category = resolved_categories[0]
    max_confidence = max(confidence_values) if confidence_values else 0.0
    reasoning = "; ".join(reason_fragments)

    return LlmResponse(
        category=primary_category,
        confidence=max_confidence,
        reasoning=reasoning,
        raw=raw_content,
        categories=resolved_categories,
    )
