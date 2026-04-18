"""Pydantic models for application configuration.

The models in this module mirror the structure of ``config.yaml`` and provide
startup-time validation for required fields and semantic constraints.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GmailConfig(BaseModel):
    """Configuration for Gmail OAuth and API scopes."""

    credentials_path: str
    token_path: str
    scopes: list[str]


class PubSubConfig(BaseModel):
    """Configuration for Google Cloud Pub/Sub integration."""

    project_id: str
    topic: str
    subscription: str
    mode: Literal["push", "pull"]
    auth_mode: Literal["default", "service_account"] = "default"
    credentials_path: str | None = None
    push_endpoint: str | None = None
    push_port: int = Field(default=8081, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_auth_mode(self) -> PubSubConfig:
        """Validate service-account auth settings when explicitly enabled."""

        if self.auth_mode == "service_account" and not self.credentials_path:
            raise ValueError(
                "pubsub.credentials_path is required when pubsub.auth_mode is 'service_account'"
            )
        return self


class LlmConfig(BaseModel):
    """Configuration for the LLM provider and prompt inputs."""

    provider: Literal["github_copilot", "openai_compatible"]
    model: str
    api_key_env: str
    base_url: str | None = None
    timeout_seconds: int = 30
    max_retries: int = 3
    system_prompt: str
    prompt_template: str


class ClassificationConfig(BaseModel):
    """Configuration for classification behavior and fallback handling."""

    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    fallback_category: str = "uncategorized"
    multi_label: bool = False
    allowlist: list[str] = Field(default_factory=list)
    blocklist: list[str] = Field(default_factory=list)


class CategoryConfig(BaseModel):
    """Single category definition used for classification and labeling."""

    name: str
    label: str
    description: str


class ProcessingConfig(BaseModel):
    """Runtime processing controls for message handling and backfill."""

    body_max_length: int = 4096
    batch_size: int = 50
    backfill_concurrency: int = 5
    archive_after_label: bool = False
    dry_run: bool = False
    backfill_progress_interval: int = Field(default=100, ge=1)


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    log_prompts: bool = False


class DatabaseConfig(BaseModel):
    """SQLite database configuration."""

    path: str = "./gmail_sorter.db"
    retention_days: int = Field(default=90, ge=1)


class ObservabilityConfig(BaseModel):
    """Ports and toggles for observability endpoints."""

    health_port: int = Field(default=8080, ge=1, le=65535)
    metrics_port: int = Field(default=9090, ge=1, le=65535)


class AlertsConfig(BaseModel):
    """Alerting and notification settings."""

    webhook_url: str | None = None


class AppConfig(BaseModel):
    """Top-level application configuration model."""

    gmail: GmailConfig
    pubsub: PubSubConfig
    llm: LlmConfig
    classification: ClassificationConfig
    categories: list[CategoryConfig]
    processing: ProcessingConfig
    logging: LoggingConfig
    database: DatabaseConfig
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)

    @model_validator(mode="after")
    def validate_unique_categories(self) -> AppConfig:
        """Validate category uniqueness for names and mapped labels."""

        names_seen: set[str] = set()
        labels_seen: set[str] = set()

        for category in self.categories:
            if category.name in names_seen:
                raise ValueError(
                    f"Duplicate category name found: {category.name}"
                )
            names_seen.add(category.name)

            if category.label in labels_seen:
                raise ValueError(
                    f"Conflicting category label found: {category.label}"
                )
            labels_seen.add(category.label)

        return self
