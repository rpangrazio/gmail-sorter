"""Prometheus metrics collection utilities."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server


class MetricsCollector:
    """Wrap application metrics exposed via ``prometheus_client``."""

    def __init__(self) -> None:
        """Create all counter and histogram metrics used by the pipeline."""

        self._registry = CollectorRegistry()
        self.emails_processed_total = Counter(
            "emails_processed_total",
            "Total number of emails processed by the system.",
            registry=self._registry,
        )
        self.emails_classified_total = Counter(
            "emails_classified_total",
            "Total number of classified emails by category.",
            ["category"],
            registry=self._registry,
        )
        self.classification_errors_total = Counter(
            "classification_errors_total",
            "Total classification errors by error type.",
            ["error_type"],
            registry=self._registry,
        )
        self.llm_latency_seconds = Histogram(
            "llm_latency_seconds",
            "Latency of LLM classification calls in seconds.",
            registry=self._registry,
        )
        self.pubsub_messages_received_total = Counter(
            "pubsub_messages_received_total",
            "Total Pub/Sub messages received by the listener.",
            registry=self._registry,
        )

    def start_http_server(self, port: int = 9090) -> None:
        """Start a Prometheus scrape endpoint on the given port."""

        start_http_server(port, registry=self._registry)
