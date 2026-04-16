"""Google Cloud Pub/Sub listener for Gmail notification processing."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

from google.api_core.exceptions import AlreadyExists
from google.cloud import pubsub_v1

from gmail_sorter.classifier.engine import ClassificationEngine
from gmail_sorter.config.models import PubSubConfig

LOGGER = logging.getLogger(__name__)


class PubSubListener:
    """Consume Pub/Sub notifications and trigger email classification."""

    def __init__(
        self,
        config: PubSubConfig,
        engine: ClassificationEngine,
        metrics: Any,
    ) -> None:
        """Initialize listener dependencies and runtime state."""

        self._config = config
        self._engine = engine
        self._metrics = metrics
        self._subscriber = pubsub_v1.SubscriberClient()
        self._publisher = pubsub_v1.PublisherClient()
        self._streaming_future: Any | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._http_server: HTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._running = False

    async def start(self) -> None:
        """Create Pub/Sub resources and start consuming notifications."""

        self._loop = asyncio.get_running_loop()
        self._ensure_topic_and_subscription()
        self._running = True

        if self._config.mode == "pull":
            await self._start_pull_mode()
            return

        await self._start_push_mode()

    async def stop(self) -> None:
        """Stop listener processing for either pull or push mode."""

        self._running = False

        if self._streaming_future is not None:
            self._streaming_future.cancel()
            self._streaming_future = None

        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
            self._http_server = None

        if self._http_thread is not None and self._http_thread.is_alive():
            self._http_thread.join(timeout=2)
            self._http_thread = None

        self._subscriber.close()
        self._publisher.close()

    def _handle_message(self, message: Any) -> None:
        """Process one Pub/Sub message and ack on successful classification."""

        pubsub_message_id = str(getattr(message, "message_id", "unknown"))
        self._increment_metric("pubsub_messages_received_total")
        current_gmail_message_id = "unknown"

        try:
            notification = self._decode_notification_payload(message.data)
            history_id = self._extract_history_id(notification)
            gmail_message_ids = self._get_message_ids_from_history(history_id)

            for gmail_message_id in gmail_message_ids:
                current_gmail_message_id = gmail_message_id
                result = self._run_classification(gmail_message_id)
                outcome = "skip" if getattr(result, "skipped", False) else "success"
                self._log_outcome(
                    pubsub_message_id=pubsub_message_id,
                    gmail_message_id=gmail_message_id,
                    outcome=outcome,
                )

            message.ack()
        except Exception:
            self._log_outcome(
                pubsub_message_id=pubsub_message_id,
                gmail_message_id=current_gmail_message_id,
                outcome="error",
                is_error=True,
            )

    async def _start_pull_mode(self) -> None:
        """Run subscriber callback consumption loop in pull mode."""

        subscription_path = self._subscription_path()
        self._streaming_future = self._subscriber.subscribe(
            subscription_path,
            callback=self._handle_message,
        )
        LOGGER.info("Pub/Sub pull listener started on %s", subscription_path)

        while self._running:
            await asyncio.sleep(0.5)

    async def _start_push_mode(self) -> None:
        """Run minimal HTTP push endpoint for Pub/Sub push delivery."""

        if self._loop is None:
            raise RuntimeError("Listener event loop is not initialized")

        listener = self

        class PushHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                if self.path != listener._push_path():
                    self.send_response(404)
                    self.end_headers()
                    return

                body_length = int(self.headers.get("Content-Length", "0"))
                raw_payload = self.rfile.read(body_length)
                push_message_id = "unknown"
                current_gmail_message_id = "unknown"

                try:
                    payload = json.loads(raw_payload.decode("utf-8"))
                    message = payload.get("message", {})
                    push_message_id = str(message.get("messageId", "unknown"))
                    encoded_data = str(message.get("data", ""))
                    notification_data = base64.b64decode(encoded_data).decode("utf-8")
                    notification = json.loads(notification_data)
                    history_id = listener._extract_history_id(notification)
                    gmail_message_ids = listener._get_message_ids_from_history(history_id)

                    for gmail_message_id in gmail_message_ids:
                        current_gmail_message_id = gmail_message_id
                        result = listener._run_classification(gmail_message_id)
                        outcome = "skip" if getattr(result, "skipped", False) else "success"
                        listener._log_outcome(
                            pubsub_message_id=push_message_id,
                            gmail_message_id=gmail_message_id,
                            outcome=outcome,
                        )

                    self.send_response(200)
                    self.end_headers()
                except Exception:
                    listener._log_outcome(
                        pubsub_message_id=push_message_id,
                        gmail_message_id=current_gmail_message_id,
                        outcome="error",
                        is_error=True,
                    )
                    self.send_response(500)
                    self.end_headers()

            def log_message(self, _format: str, *_args: Any) -> None:
                return

        port = int(self._config.push_port)
        self._http_server = HTTPServer(("0.0.0.0", port), PushHandler)
        self._http_thread = threading.Thread(target=self._http_server.serve_forever, daemon=True)
        self._http_thread.start()
        LOGGER.info(
            "Pub/Sub push listener started",
            extra={
                "context": {
                    "port": port,
                    "endpoint": self._push_path(),
                }
            },
        )

        while self._running:
            await asyncio.sleep(0.5)

    def _ensure_topic_and_subscription(self) -> None:
        """Create topic and subscription when missing; reuse existing otherwise."""

        topic_path = self._topic_path()
        subscription_path = self._subscription_path()

        try:
            self._publisher.create_topic(name=topic_path)
        except AlreadyExists:
            pass

        subscription_request: dict[str, Any] = {
            "name": subscription_path,
            "topic": topic_path,
        }

        if self._config.mode == "push":
            push_endpoint = self._config.push_endpoint
            if isinstance(push_endpoint, str) and push_endpoint:
                subscription_request["push_config"] = pubsub_v1.types.PushConfig(
                    push_endpoint=push_endpoint
                )

        try:
            self._subscriber.create_subscription(request=subscription_request)
        except AlreadyExists:
            pass

    def _run_classification(self, gmail_message_id: str) -> Any:
        """Execute async classification from synchronous callback context."""

        if self._loop is None:
            raise RuntimeError("Listener event loop is not initialized")

        future = asyncio.run_coroutine_threadsafe(
            self._engine.classify_message(gmail_message_id),
            self._loop,
        )
        return future.result()

    def _push_path(self) -> str:
        """Resolve configured push endpoint path for local HTTP routing."""

        configured = self._config.push_endpoint
        if not configured:
            return "/pubsub"

        parsed = urlparse(configured)
        if parsed.scheme and parsed.netloc:
            return parsed.path or "/pubsub"

        return configured if configured.startswith("/") else f"/{configured}"

    def _log_outcome(
        self,
        pubsub_message_id: str,
        gmail_message_id: str,
        outcome: str,
        is_error: bool = False,
    ) -> None:
        """Emit PRD-required Pub/Sub processing outcome logs."""

        log_extra = {
            "context": {
                "pubsub_message_id": pubsub_message_id,
                "gmail_message_id": gmail_message_id,
                "outcome": outcome,
            }
        }
        if is_error:
            LOGGER.exception("Pub/Sub message processing failed", extra=log_extra)
            return

        LOGGER.info("Pub/Sub message processing outcome", extra=log_extra)

    @staticmethod
    def _decode_notification_payload(raw_data: bytes) -> dict[str, Any]:
        """Decode Pub/Sub payload bytes into a notification dictionary."""

        if not raw_data:
            return {}
        return json.loads(raw_data.decode("utf-8"))

    @staticmethod
    def _extract_history_id(notification: dict[str, Any]) -> str:
        """Extract and validate Gmail history ID from notification payload."""

        history_id = notification.get("historyId")
        if history_id is None:
            raise ValueError("Pub/Sub notification is missing historyId")
        return str(history_id)

    def _get_message_ids_from_history(self, history_id: str) -> list[str]:
        """Resolve newly added Gmail message IDs from Gmail history API."""

        message_ids: list[str] = []
        page_token: str | None = None

        while True:
            history_response = self._engine._gmail_client.list_history(  # type: ignore[attr-defined]
                start_history_id=history_id,
                page_token=page_token,
            )
            for item in history_response.get("history", []):
                for message_added in item.get("messagesAdded", []):
                    message = message_added.get("message", {})
                    message_id = message.get("id")
                    if message_id:
                        message_ids.append(str(message_id))

            page_token = history_response.get("nextPageToken")
            if page_token is None:
                break

        return message_ids

    def _topic_path(self) -> str:
        """Return fully-qualified Pub/Sub topic path."""

        return self._publisher.topic_path(self._config.project_id, self._config.topic)

    def _subscription_path(self) -> str:
        """Return fully-qualified Pub/Sub subscription path."""

        return self._subscriber.subscription_path(
            self._config.project_id,
            self._config.subscription,
        )

    def _increment_metric(self, metric_name: str) -> None:
        """Increment an optional counter metric when available."""

        metric = getattr(self._metrics, metric_name, None)
        if metric is None:
            return
        increment = getattr(metric, "inc", None)
        if callable(increment):
            increment()
