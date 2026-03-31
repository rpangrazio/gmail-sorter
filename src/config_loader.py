"""
Configuration loader for Gmail AI Sorter.

Reads and validates the YAML configuration file, providing typed dataclasses
for use throughout the application.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Category:
    """Represents a single email classification category."""

    name: str
    """Short identifier used as the classification label (e.g., 'work')."""

    label: str
    """Gmail label name to apply (supports nested labels via '/', e.g., 'AI-Sorted/Work')."""

    description: str
    """Natural-language description used in the Claude classification prompt."""

    keywords: List[str] = field(default_factory=list)
    """Optional hint keywords included in the classification prompt."""


@dataclass
class Config:
    """Top-level application configuration."""

    google_project_id: str
    """GCP project ID that owns the Pub/Sub topic and subscription."""

    pubsub_subscription: str
    """Full Pub/Sub subscription resource path (e.g., 'projects/my-proj/subscriptions/my-sub')."""

    gmail_watch_topic: str
    """Full Pub/Sub topic resource path that Gmail publishes change notifications to."""

    categories: List[Category]
    """Ordered list of email categories. Earlier entries take precedence when ambiguous."""

    max_emails_per_poll: int = 10
    """Maximum number of emails to process per Pub/Sub pull cycle."""

    log_level: str = "INFO"
    """Python logging level string (DEBUG, INFO, WARNING, ERROR)."""

    dry_run: bool = False
    """When True, classify emails but do not apply any Gmail labels."""

    ai_provider: str = "anthropic"
    """AI provider to use for classification: 'anthropic' or 'openai'."""

    anthropic_model: str = "claude-opus-4-6"
    """Anthropic model identifier used when ai_provider is 'anthropic'."""

    openai_model: str = "gpt-4o"
    """OpenAI model identifier used when ai_provider is 'openai'."""

    state_backend: str = "json"
    """Storage backend for persisting application state: 'json', 'sqlite', or 'postgres'."""


def load_config(config_path: str) -> Config:
    """
    Load and validate the application configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        A validated Config instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If required fields are missing or invalid.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            "Copy config/config.yaml.example to config/config.yaml and fill in your values."
        )

    logger.debug("Loading configuration from %s", config_path)

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("Configuration file must contain a YAML mapping at the top level.")

    _require_fields(raw, ["google_project_id", "pubsub_subscription", "gmail_watch_topic", "categories"])

    # Validate Pub/Sub resource paths
    for field_name in ("pubsub_subscription", "gmail_watch_topic"):
        value = raw[field_name]
        if not isinstance(value, str) or not value.startswith("projects/"):
            raise ValueError(
                f"'{field_name}' must be a full resource path starting with 'projects/', "
                f"got: {value!r}"
            )

    # Parse categories
    raw_categories = raw.get("categories", [])
    if not isinstance(raw_categories, list) or len(raw_categories) == 0:
        raise ValueError("'categories' must be a non-empty list.")

    categories = []
    seen_names: set = set()
    for i, raw_cat in enumerate(raw_categories):
        _require_fields(raw_cat, ["name", "label", "description"], context=f"categories[{i}]")

        name = str(raw_cat["name"]).strip().lower()
        if name in seen_names:
            raise ValueError(f"Duplicate category name '{name}' at index {i}.")
        seen_names.add(name)

        description = str(raw_cat["description"]).strip()
        if len(description) < 20:
            raise ValueError(
                f"Category '{name}' description is too short (minimum 20 characters)."
            )

        keywords = [str(k) for k in raw_cat.get("keywords", [])]

        categories.append(
            Category(
                name=name,
                label=str(raw_cat["label"]).strip(),
                description=description,
                keywords=keywords,
            )
        )

    # Validate ai_provider value.
    ai_provider = str(raw.get("ai_provider", "anthropic")).strip().lower()
    if ai_provider not in {"anthropic", "openai"}:
        raise ValueError(
            f"'ai_provider' must be 'anthropic' or 'openai', got: {ai_provider!r}"
        )

    # Validate state_backend value.
    state_backend = str(raw.get("state_backend", "json")).strip().lower()
    if state_backend not in {"json", "sqlite", "postgres"}:
        raise ValueError(
            f"'state_backend' must be 'json', 'sqlite', or 'postgres', "
            f"got: {state_backend!r}"
        )

    config = Config(
        google_project_id=str(raw["google_project_id"]).strip(),
        pubsub_subscription=str(raw["pubsub_subscription"]).strip(),
        gmail_watch_topic=str(raw["gmail_watch_topic"]).strip(),
        categories=categories,
        max_emails_per_poll=int(raw.get("max_emails_per_poll", 10)),
        log_level=str(raw.get("log_level", "INFO")).upper(),
        dry_run=bool(raw.get("dry_run", False)),
        ai_provider=ai_provider,
        anthropic_model=str(raw.get("anthropic_model", "claude-opus-4-6")).strip(),
        openai_model=str(raw.get("openai_model", "gpt-4o")).strip(),
        state_backend=state_backend,
    )

    logger.info(
        "Configuration loaded: %d categories, project=%s",
        len(config.categories),
        config.google_project_id,
    )
    return config


def _require_fields(mapping: dict, fields: List[str], context: str = "config") -> None:
    """Assert that all named fields are present in *mapping*."""
    for field_name in fields:
        if field_name not in mapping or mapping[field_name] is None:
            raise ValueError(f"Required field '{field_name}' is missing in {context}.")
