"""Email classification orchestration pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from gmail_sorter.classifier.idempotency import IdempotencyChecker
from gmail_sorter.config.models import AppConfig
from gmail_sorter.db.repository import ClassificationRecord, Database, DlqEntry
from gmail_sorter.llm.response_parser import LlmResponse, parse_response
from gmail_sorter.observability.error_taxonomy import classify_exception, normalize_error_type
from gmail_sorter.processor.email_parser import ProcessedEmail, process_message
from gmail_sorter.processor.prompt_builder import PromptBuilder
from gmail_sorter.utils.security import create_tls12_context, ensure_tls12_minimum
from gmail_sorter.utils.security import is_domain_allowed

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ClassificationResult:
    """Classification outcome returned by ``ClassificationEngine``."""

    message_id: str
    category: str
    confidence: float
    label_applied: str
    skipped: bool
    duration_ms: int


class ClassificationEngine:
    """Coordinate message parsing, LLM classification, and label application."""

    def __init__(
        self,
        config: AppConfig,
        gmail_client: Any,
        llm_client: Any,
        db: Database,
        label_map: dict[str, str],
        idempotency_checker: IdempotencyChecker,
        prompt_builder: PromptBuilder,
        metrics: Any,
    ) -> None:
        """Initialize the engine with all required pipeline dependencies."""

        self._config = config
        self._gmail_client = gmail_client
        self._llm_client = llm_client
        self._db = db
        self._label_map = label_map
        self._idempotency_checker = idempotency_checker
        self._prompt_builder = prompt_builder
        self._metrics = metrics

    async def classify_message(self, message_id: str) -> ClassificationResult:
        """Classify one Gmail message and apply the mapped label."""

        started = time.perf_counter()
        current_message_id = message_id

        try:
            raw_message = self._gmail_client.get_message(message_id)

            idempotency_email = ProcessedEmail(
                message_id=str(raw_message.get("id", message_id)),
                thread_id=str(raw_message.get("threadId", "")),
                sender="",
                subject="",
                date="",
                body="",
                headers={},
                raw_label_ids=[str(label) for label in raw_message.get("labelIds", [])],
            )

            current_message_id = idempotency_email.message_id
            if self._idempotency_checker.is_processed(idempotency_email):
                return self._result(
                    message_id=idempotency_email.message_id,
                    category="",
                    confidence=0.0,
                    label_applied="",
                    skipped=True,
                    started=started,
                )

            email = process_message(raw_message, self._config.processing)
            current_message_id = email.message_id

            allowlist, blocklist = self._sender_domain_lists()
            if not is_domain_allowed(email.sender, allowlist=allowlist, blocklist=blocklist):
                LOGGER.info("Skipping message due to sender domain policy: %s", email.message_id)
                return self._result(
                    message_id=email.message_id,
                    category="",
                    confidence=0.0,
                    label_applied="",
                    skipped=True,
                    started=started,
                )

            system_prompt, user_prompt = self._prompt_builder.build(email)
            llm_output = await self._llm_client.classify(system_prompt, user_prompt)

            raw_content = self._extract_raw_content(llm_output)
            parsed = parse_response(
                raw_content=raw_content,
                valid_categories=[category.name for category in self._config.categories],
                fallback=self._config.classification.fallback_category,
                threshold=self._config.classification.confidence_threshold,
                multi_label=self._config.classification.multi_label,
            )

            resolved_categories = self._resolve_categories(parsed)
            labels_applied = self._resolve_labels(resolved_categories)
            primary_label = labels_applied[0] if labels_applied else ""

            if self._config.processing.dry_run:
                LOGGER.info(
                    "Dry-run classification: message_id=%s category=%s label=%s confidence=%.3f",
                    email.message_id,
                    ",".join(resolved_categories),
                    ",".join(labels_applied),
                    parsed.confidence,
                )
                self._increment_metric("emails_processed_total")
                for category in resolved_categories:
                    self._increment_metric("emails_classified_total", category)
                return self._result(
                    message_id=email.message_id,
                    category=resolved_categories[0],
                    confidence=parsed.confidence,
                    label_applied=primary_label,
                    skipped=False,
                    started=started,
                )

            for index, label_id in enumerate(labels_applied):
                self._gmail_client.apply_label(
                    email.message_id,
                    label_id,
                    archive=self._config.processing.archive_after_label and index == 0,
                )

            duration_ms = int((time.perf_counter() - started) * 1000)
            self._db.upsert_classification(
                ClassificationRecord(
                    message_id=email.message_id,
                    gmail_thread_id=email.thread_id,
                    timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    category=",".join(resolved_categories),
                    confidence=parsed.confidence,
                    model_used=self._config.llm.model,
                    prompt_template_hash=self._prompt_builder.template_hash(),
                    label_applied=",".join(labels_applied),
                    processing_duration_ms=duration_ms,
                )
            )

            self._increment_metric("emails_processed_total")
            for category in resolved_categories:
                self._increment_metric("emails_classified_total", category)

            return ClassificationResult(
                message_id=email.message_id,
                category=resolved_categories[0],
                confidence=parsed.confidence,
                label_applied=primary_label,
                skipped=False,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            error_type = self._error_type(exc)
            LOGGER.exception(
                "Classification pipeline failed",
                extra={
                    "error_type": error_type,
                    "context": {
                        "message_id": current_message_id,
                        "operation": "classify_message",
                    },
                },
            )
            self._db.add_to_dlq(
                DlqEntry(
                    id=None,
                    message_id=current_message_id,
                    error_type=error_type,
                    error_message=str(exc) or exc.__class__.__name__,
                    attempts=1,
                )
            )
            self._increment_error_metric(error_type)
            await self._notify_critical_error(
                error_type=error_type,
                message_id=current_message_id,
                description=str(exc) or exc.__class__.__name__,
            )
            raise

    @staticmethod
    def _extract_raw_content(llm_output: Any) -> str:
        """Normalize LLM output into raw response text for parser validation."""

        if isinstance(llm_output, LlmResponse):
            return llm_output.raw
        if isinstance(llm_output, str):
            return llm_output
        raw = getattr(llm_output, "raw", None)
        if isinstance(raw, str):
            return raw
        return str(llm_output)

    def _sender_domain_lists(self) -> tuple[list[str], list[str]]:
        """Return sender-domain allowlist and blocklist from typed config."""

        return (
            [str(item) for item in self._config.classification.allowlist],
            [str(item) for item in self._config.classification.blocklist],
        )

    def _resolve_categories(self, parsed: LlmResponse) -> list[str]:
        """Resolve classification categories based on single/multi-label mode."""

        categories = parsed.categories if self._config.classification.multi_label else [parsed.category]
        deduplicated: list[str] = []
        for category in categories:
            value = str(category).strip()
            if value and value not in deduplicated:
                deduplicated.append(value)

        if not deduplicated:
            deduplicated.append(self._config.classification.fallback_category)

        return deduplicated

    def _resolve_labels(self, categories: list[str]) -> list[str]:
        """Map categories to configured label IDs with fallback support."""

        fallback_label = self._label_map.get(self._config.classification.fallback_category, "")
        labels: list[str] = []
        for category in categories:
            label = self._label_map.get(category, fallback_label)
            if label and label not in labels:
                labels.append(label)

        if not labels and fallback_label:
            labels.append(fallback_label)

        return labels

    def _result(
        self,
        message_id: str,
        category: str,
        confidence: float,
        label_applied: str,
        skipped: bool,
        started: float,
    ) -> ClassificationResult:
        """Build a standardized classification result object."""

        return ClassificationResult(
            message_id=message_id,
            category=category,
            confidence=confidence,
            label_applied=label_applied,
            skipped=skipped,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def _increment_metric(self, metric_name: str, category: str | None = None) -> None:
        """Increment metrics counters when a metrics collector is configured."""

        metric = getattr(self._metrics, metric_name, None)
        if metric is None:
            return

        if category is None:
            increment = getattr(metric, "inc", None)
            if callable(increment):
                increment()
            return

        labels = getattr(metric, "labels", None)
        if callable(labels):
            labelled_metric = labels(category=category)
            increment = getattr(labelled_metric, "inc", None)
            if callable(increment):
                increment()

    def _increment_error_metric(self, error_type: str) -> None:
        """Increment the classified error counter when metrics are configured."""

        metric = getattr(self._metrics, "classification_errors_total", None)
        labels = getattr(metric, "labels", None)
        if callable(labels):
            labelled_metric = labels(error_type=normalize_error_type(error_type))
            increment = getattr(labelled_metric, "inc", None)
            if callable(increment):
                increment()

    async def _notify_critical_error(self, error_type: str, message_id: str, description: str) -> None:
        """Send optional webhook notifications for critical pipeline failures."""

        webhook_url = self._config.alerts.webhook_url
        if not webhook_url:
            return

        payload = {
            "error_type": normalize_error_type(error_type),
            "message_id": message_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "description": description,
        }

        try:
            tls_context = ensure_tls12_minimum(create_tls12_context())
            async with httpx.AsyncClient(timeout=5.0, verify=tls_context) as client:
                response = await client.post(webhook_url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError:
            LOGGER.warning(
                "Failed to deliver critical-error webhook notification",
                extra={
                    "error_type": "api_error",
                    "context": {
                        "message_id": message_id,
                        "operation": "critical_error_webhook",
                    },
                },
                exc_info=True,
            )

    @staticmethod
    def _error_type(exc: Exception) -> str:
        """Map an exception to the PRD-aligned error type taxonomy."""

        return classify_exception(exc)
