"""Helpers for PRD-aligned error taxonomy classification."""

from __future__ import annotations

from typing import Final

ERROR_TYPES: Final[set[str]] = {
    "auth_error",
    "api_error",
    "llm_error",
    "config_error",
    "pubsub_error",
}
DEFAULT_ERROR_TYPE: Final[str] = "api_error"


def normalize_error_type(error_type: str | None) -> str:
    """Return a valid PRD error type label for logs and metrics."""

    if not error_type:
        return DEFAULT_ERROR_TYPE

    normalized = str(error_type).strip().lower()
    if normalized in ERROR_TYPES:
        return normalized
    return DEFAULT_ERROR_TYPE


def classify_exception(exc: BaseException) -> str:
    """Map an exception instance to one of the required error labels."""

    class_name = exc.__class__.__name__.lower()
    module_name = exc.__class__.__module__.lower()
    combined = f"{module_name}.{class_name}"

    if any(token in combined for token in ("pubsub", "subscriber", "publisher")):
        return "pubsub_error"

    if class_name in {"systemexit", "validationerror"} or any(
        token in combined for token in ("pydantic", "yaml", "config")
    ):
        return "config_error"

    if any(token in combined for token in ("llm", "timeout")):
        return "llm_error"

    if any(token in combined for token in ("oauth", "credential", "auth", "scope", "refresh")):
        return "auth_error"

    return DEFAULT_ERROR_TYPE
