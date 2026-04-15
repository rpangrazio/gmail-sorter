"""LLM response parsing utilities.

This module normalizes raw model output into a typed response object and
applies category and confidence guardrails required by the classification
pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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
) -> LlmResponse:
    """Parse and validate a model response against classification constraints."""

    payload = _extract_json_payload(raw_content)

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
    )
