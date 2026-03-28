"""
Google Cloud Pub/Sub pull subscriber.

Listens for Gmail change notifications on a Pub/Sub pull subscription and
delivers decoded notification payloads to a caller-supplied callback function.

Gmail publishes a small JSON notification whenever the watched mailbox changes::

    {"emailAddress": "user@gmail.com", "historyId": "12345678"}

This module handles the pull loop, acknowledgement, and connection-error
recovery so that :mod:`src.main` only needs to provide a processing callback.
"""

import base64
import json
import logging
import time
from typing import Any, Callable, Dict, Optional

from google.api_core.exceptions import DeadlineExceeded, ServiceUnavailable
from google.cloud import pubsub_v1
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

# How long (seconds) to wait for messages on each pull request.
# Pub/Sub long-polling: if no messages arrive within this window, an empty
# response is returned and the loop continues.
_PULL_TIMEOUT_SECONDS = 30

# Maximum messages to retrieve per pull request.
_MAX_MESSAGES = 10

# Delay (seconds) before retrying after a transient connection error.
_ERROR_RETRY_DELAY = 5.0


class PubSubClient:
    """
    Pull-based Pub/Sub subscriber that delivers Gmail change notifications.

    Uses the synchronous ``google-cloud-pubsub`` client, which is sufficient
    for the low-volume single-user use-case (one notification per incoming email).

    Args:
        subscription_path: Full Pub/Sub subscription resource path, e.g.
            ``"projects/my-proj/subscriptions/gmail-sorter-sub"``.
        credentials: Authenticated Google OAuth2 credentials used to
            authorize Pub/Sub API calls.
    """

    def __init__(self, subscription_path: str, credentials: Credentials) -> None:
        self._subscription_path = subscription_path
        self._subscriber = pubsub_v1.SubscriberClient(credentials=credentials)

    def run_forever(
        self,
        callback: Callable[[Dict[str, Any]], None],
        stop_event: Optional[Any] = None,
    ) -> None:
        """
        Block indefinitely, calling *callback* for each Gmail notification.

        The loop pulls messages in batches, delivers each payload to
        *callback*, then acknowledges all messages in the batch.
        Acknowledgement happens even if *callback* raises an exception, to
        prevent poison-pill messages from blocking the queue forever.

        Args:
            callback: A function that accepts a single ``dict`` notification
                payload ``{"emailAddress": ..., "historyId": ...}``.
            stop_event: An optional :class:`threading.Event`.  When set,
                the loop exits cleanly after finishing the current batch.
        """
        logger.info(
            "Pub/Sub pull loop started on subscription: %s", self._subscription_path
        )

        while not (stop_event and stop_event.is_set()):
            try:
                self._pull_and_process(callback)
            except DeadlineExceeded:
                # Normal: no messages arrived within the timeout window.
                logger.debug("Pub/Sub pull timeout (no new messages); continuing loop.")
            except ServiceUnavailable as exc:
                logger.warning(
                    "Pub/Sub service temporarily unavailable: %s. "
                    "Retrying in %.0fs...",
                    exc,
                    _ERROR_RETRY_DELAY,
                )
                time.sleep(_ERROR_RETRY_DELAY)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Unexpected error in Pub/Sub loop: %s. Retrying in %.0fs...",
                    exc,
                    _ERROR_RETRY_DELAY,
                    exc_info=True,
                )
                time.sleep(_ERROR_RETRY_DELAY)

        logger.info("Pub/Sub pull loop stopped.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _pull_and_process(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Perform a single pull request and invoke *callback* for each message.

        All received messages are acknowledged regardless of whether
        *callback* succeeds, to prevent indefinite redelivery of bad messages.

        Args:
            callback: Notification payload handler.
        """
        response = self._subscriber.pull(
            request={
                "subscription": self._subscription_path,
                "max_messages": _MAX_MESSAGES,
            },
            timeout=_PULL_TIMEOUT_SECONDS,
        )

        if not response.received_messages:
            return

        ack_ids = []
        for received_message in response.received_messages:
            ack_ids.append(received_message.ack_id)
            payload = self._decode_message(received_message.message)
            if payload is None:
                logger.warning(
                    "Skipping Pub/Sub message with unparseable payload "
                    "(message_id=%s).",
                    received_message.message.message_id,
                )
                continue

            logger.debug(
                "Received Pub/Sub notification: emailAddress=%s, historyId=%s",
                payload.get("emailAddress"),
                payload.get("historyId"),
            )

            try:
                callback(payload)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Error processing notification (historyId=%s): %s",
                    payload.get("historyId"),
                    exc,
                    exc_info=True,
                )
            # Always acknowledge — see docstring above.

        # Acknowledge the entire batch in one request.
        self._subscriber.acknowledge(
            request={
                "subscription": self._subscription_path,
                "ack_ids": ack_ids,
            }
        )
        logger.debug("Acknowledged %d Pub/Sub messages.", len(ack_ids))

    @staticmethod
    def _decode_message(message) -> Optional[Dict[str, Any]]:
        """
        Decode a Pub/Sub message's base64-encoded data field to a dict.

        Gmail always encodes the notification JSON in base64.

        Args:
            message: A ``google.cloud.pubsub_v1.types.PubsubMessage``.

        Returns:
            Decoded dict, or None on parse failure.
        """
        try:
            raw_bytes = base64.b64decode(message.data)
            return json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to decode Pub/Sub message data: %s", exc)
            return None
