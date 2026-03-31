"""
Gmail AI Sorter — main entry point.

Wires together authentication, Gmail API, Cloud Pub/Sub, and the Claude
classifier into a single long-running agent that:

1. Loads configuration from a YAML file.
2. Authenticates with Google OAuth2.
3. Ensures all configured Gmail labels exist.
4. Registers (or renews) a Gmail push-notification watch.
5. Pulls Gmail change notifications from Cloud Pub/Sub.
6. For each notification, fetches new inbox messages via the History API.
7. Classifies each message with Claude AI.
8. Applies the matching Gmail label.
9. Persists the history cursor so the agent can resume after restarts.

Usage::

    # First-run OAuth2 authorization:
    python -m src.main --setup

    # Normal operation:
    python -m src.main [--config /path/to/config.yaml]
"""

import argparse
import logging
import os
import sys
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Set

from dotenv import load_dotenv
from googleapiclient.discovery import build

from src.auth import GoogleAuthManager
from src.classifier import BaseClassifier, create_classifier
from src.config_loader import load_config
from src.gmail_client import GmailClient, HistoryExpiredError
from src.label_manager import LabelManager
from src.pubsub_client import PubSubClient
from src.state_manager import BaseStateManager, create_state_manager

# How often (seconds) the watch-renewal background thread wakes up to check
# whether the Gmail watch needs to be renewed.
_WATCH_CHECK_INTERVAL_SECONDS = 3600  # 1 hour

# Maximum number of recently processed message IDs to track for deduplication.
# Pub/Sub guarantees at-least-once delivery; this set prevents double-labelling.
_DEDUP_MAX_SIZE = 500


def main() -> None:
    """Application entry point."""
    args = _parse_args()

    # Load .env file if present (useful for local development).
    load_dotenv()

    config_path = args.config or os.environ.get("CONFIG_PATH", "/app/config/config.yaml")
    config = load_config(config_path)

    # Configure logging.
    log_level_str = os.environ.get("LOG_LEVEL", config.log_level).upper()
    _configure_logging(log_level_str)

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Gmail AI Sorter starting up")
    logger.info("Config: %s", config_path)
    logger.info(
        "Categories: %s", ", ".join(c.name for c in config.categories)
    )
    logger.info(
        "AI provider: %s (model: %s)",
        config.ai_provider,
        config.copilot_model if config.ai_provider == "copilot" else config.openai_model,
    )
    if config.dry_run:
        logger.warning("DRY RUN mode enabled — labels will NOT be applied.")
    logger.info("=" * 60)

    # Resolve file paths from environment or defaults.
    credentials_path = os.environ.get(
        "GOOGLE_CREDENTIALS_PATH", "/credentials/credentials.json"
    )
    token_path = os.environ.get("GOOGLE_TOKEN_PATH", "/data/token.json")
    state_file_path = os.environ.get("STATE_FILE_PATH", "/data/state.json")
    sqlite_db_path = os.environ.get("SQLITE_DB_PATH", "/data/gmail_sorter.db")
    database_url = os.environ.get("DATABASE_URL", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    openai_base_url = os.environ.get("OPENAI_BASE_URL", "")

    # Validate that the required API key for the configured provider is present.
    if config.ai_provider == "copilot" and not github_token:
        logger.error(
            "GITHUB_TOKEN is not set but ai_provider='copilot'. "
            "Set it in your .env file or Docker environment."
        )
        sys.exit(1)
    if config.ai_provider == "openai" and not openai_api_key:
        logger.error(
            "OPENAI_API_KEY is not set but ai_provider='openai'. "
            "Set it in your .env file or Docker environment."
        )
        sys.exit(1)

    # Authenticate with Google.
    auth_manager = GoogleAuthManager(
        credentials_path=credentials_path,
        token_path=token_path,
    )

    if args.setup:
        logger.info("Running first-time OAuth2 authorization setup...")
        creds = auth_manager.get_credentials()
        logger.info("Setup complete. Token stored at %s.", token_path)
        logger.info("You can now start the agent normally (without --setup).")
        return

    creds = auth_manager.get_credentials()

    # Build service clients.
    gmail_service = build("gmail", "v1", credentials=creds)
    gmail_client = GmailClient(gmail_service)
    state_manager = _create_state_manager(config.state_backend, state_file_path, sqlite_db_path, database_url)
    label_manager = LabelManager(gmail_service)
    classifier = create_classifier(
        config=config,
        github_token=github_token,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url or None,
    )
    pubsub_client = PubSubClient(
        subscription_path=config.pubsub_subscription,
        credentials=creds,
    )

    # Warm the label cache — creates any missing labels up front.
    label_names = [cat.label for cat in config.categories]
    label_manager.warm_cache(label_names)

    # Bootstrap history ID if this is the first run.
    _bootstrap_history_id(gmail_client, state_manager)

    # Register Gmail watch.
    gmail_client.ensure_watch(config.gmail_watch_topic, state_manager)

    # Start background watch-renewal thread.
    stop_event = threading.Event()
    watch_thread = threading.Thread(
        target=_watch_renewal_loop,
        args=(gmail_client, config.gmail_watch_topic, state_manager, stop_event),
        name="watch-renewal",
        daemon=True,
    )
    watch_thread.start()

    # Build processing context and start the Pub/Sub loop.
    context = _ProcessingContext(
        gmail_client=gmail_client,
        classifier=classifier,
        label_manager=label_manager,
        state_manager=state_manager,
        config_categories={cat.name: cat.label for cat in config.categories},
        dry_run=config.dry_run,
    )

    logger.info("Entering Pub/Sub pull loop — waiting for Gmail notifications...")
    try:
        pubsub_client.run_forever(
            callback=context.handle_notification,
            stop_event=stop_event,
        )
    except KeyboardInterrupt:
        logger.info("Received shutdown signal.")
    finally:
        stop_event.set()
        logger.info("Gmail AI Sorter stopped.")


# ------------------------------------------------------------------
# Processing context
# ------------------------------------------------------------------

class _ProcessingContext:
    """
    Holds shared state for the notification processing callback.

    Separating this from ``main()`` makes the callback stateful (dedup set,
    category→label map) without using module-level globals.
    """

    def __init__(
        self,
        gmail_client: GmailClient,
        classifier: BaseClassifier,
        label_manager: LabelManager,
        state_manager: BaseStateManager,
        config_categories: Dict[str, str],
        dry_run: bool,
    ) -> None:
        self._gmail = gmail_client
        self._classifier: BaseClassifier = classifier
        self._labels = label_manager
        self._state = state_manager
        self._categories = config_categories  # name → label_name
        self._dry_run = dry_run
        self._processed_ids: Deque[str] = deque(maxlen=_DEDUP_MAX_SIZE)
        self._processed_set: Set[str] = set()
        self._logger = logging.getLogger(__name__)

    def handle_notification(self, notification: Dict[str, Any]) -> None:
        """
        Process a single Gmail change notification from Pub/Sub.

        Fetches new messages since the last known history ID, classifies
        each one, and applies labels.

        Args:
            notification: Decoded Pub/Sub message payload::

                {"emailAddress": "user@gmail.com", "historyId": "12345"}
        """
        history_id = notification.get("historyId")
        email_address = notification.get("emailAddress", "unknown")

        self._logger.debug(
            "Processing notification: emailAddress=%s, historyId=%s",
            email_address,
            history_id,
        )

        current_history_id = self._state.get_history_id()
        if not current_history_id:
            self._logger.warning(
                "No stored history ID — cannot fetch history. "
                "Storing current historyId and waiting for next notification."
            )
            if history_id:
                self._state.set_history_id(history_id)
            return

        # Fetch all new messages since the last cursor.
        try:
            message_ids, max_history_id = self._gmail.list_new_messages(
                current_history_id
            )
        except HistoryExpiredError as exc:
            self._logger.warning("%s Resetting history cursor.", exc)
            # Reset to the historyId from the notification.
            if history_id:
                self._state.set_history_id(history_id)
            return

        if not message_ids:
            self._logger.debug("No new inbox messages in this history batch.")
            if max_history_id > current_history_id:
                self._state.set_history_id(max_history_id)
            return

        self._logger.info(
            "Found %d new message(s) to process.", len(message_ids)
        )

        for msg_id in message_ids:
            self._process_message(msg_id)

        # Advance the history cursor past everything we just processed.
        self._state.set_history_id(max_history_id)

    def _process_message(self, message_id: str) -> None:
        """
        Fetch, classify, and label a single message.

        Skips messages already processed in this session (dedup).

        Args:
            message_id: Gmail message ID string.
        """
        if message_id in self._processed_set:
            self._logger.debug("Skipping already-processed message: %s", message_id)
            return

        try:
            email_data = self._gmail.get_message(message_id)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Failed to fetch message %s: %s", message_id, exc)
            return

        subject = email_data.get("subject", "(no subject)")
        sender = email_data.get("from_", "(unknown)")

        self._logger.info(
            "Processing message %s | From: %s | Subject: %s",
            message_id,
            sender,
            subject,
        )

        try:
            category_name = self._classifier.classify(email_data)
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "Classification failed for message %s: %s", message_id, exc
            )
            return

        if category_name is None:
            self._logger.info(
                "Message %s → no matching category (skipping label).", message_id
            )
        else:
            label_name = self._categories.get(category_name)
            if not label_name:
                self._logger.warning(
                    "Category '%s' has no configured label; skipping.", category_name
                )
            elif self._dry_run:
                self._logger.info(
                    "[DRY RUN] Would apply label '%s' to message %s.",
                    label_name,
                    message_id,
                )
            else:
                try:
                    label_id = self._labels.get_or_create_label(label_name)
                    self._gmail.apply_label(message_id, label_id)
                    self._logger.info(
                        "Labelled message %s as '%s' (label: '%s').",
                        message_id,
                        category_name,
                        label_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    self._logger.error(
                        "Failed to apply label '%s' to message %s: %s",
                        label_name,
                        message_id,
                        exc,
                    )

        # Mark as processed (dedup).
        if len(self._processed_ids) >= _DEDUP_MAX_SIZE:
            oldest = self._processed_ids[0]
            self._processed_set.discard(oldest)
        self._processed_ids.append(message_id)
        self._processed_set.add(message_id)


# ------------------------------------------------------------------
# Background threads
# ------------------------------------------------------------------

def _watch_renewal_loop(
    gmail_client: GmailClient,
    topic_name: str,
    state_manager: BaseStateManager,
    stop_event: threading.Event,
) -> None:
    """
    Background thread that renews the Gmail watch before it expires.

    Gmail watch registrations expire after 7 days.  This thread checks
    every hour and renews when the expiry is within 24 hours.

    Args:
        gmail_client: Authenticated :class:`~src.gmail_client.GmailClient`.
        topic_name: Pub/Sub topic name for the watch registration.
        state_manager: :class:`~src.state_manager.StateManager` for persisting expiry.
        stop_event: Set this event to stop the thread cleanly.
    """
    logger = logging.getLogger(__name__)
    logger.debug("Watch renewal thread started.")
    while not stop_event.wait(timeout=_WATCH_CHECK_INTERVAL_SECONDS):
        try:
            gmail_client.ensure_watch(topic_name, state_manager)
        except Exception as exc:  # noqa: BLE001
            logger.error("Watch renewal failed: %s", exc, exc_info=True)
    logger.debug("Watch renewal thread stopped.")


# ------------------------------------------------------------------
# Startup helpers
# ------------------------------------------------------------------

def _create_state_manager(
    backend: str,
    state_file_path: str,
    sqlite_db_path: str,
    database_url: str,
) -> BaseStateManager:
    """
    Instantiate the configured state manager backend.

    Args:
        backend: One of ``"json"``, ``"sqlite"``, or ``"postgres"``.
        state_file_path: Path used by the JSON backend.
        sqlite_db_path: Path used by the SQLite backend.
        database_url: Connection URL used by the PostgreSQL backend.

    Returns:
        A fully initialised :class:`~src.state_manager.BaseStateManager`.
    """
    logger = logging.getLogger(__name__)

    if backend == "postgres":
        if not database_url:
            logger.error(
                "state_backend='postgres' requires DATABASE_URL to be set."
            )
            sys.exit(1)
        logger.info("State backend: PostgreSQL")
        return create_state_manager("postgres", dsn=database_url)

    if backend == "sqlite":
        logger.info("State backend: SQLite (%s)", sqlite_db_path)
        return create_state_manager("sqlite", db_path=sqlite_db_path)

    logger.info("State backend: JSON (%s)", state_file_path)
    return create_state_manager("json", state_file_path=state_file_path)


def _bootstrap_history_id(
    gmail_client: GmailClient, state_manager: BaseStateManager
) -> None:
    """
    Set the initial history cursor if none is stored.

    Called on startup.  Fetches the current ``historyId`` from the Gmail
    profile and stores it so the first notification can call history.list().

    Note: Emails received *before* this initial cursor are not processed.
    Only emails received *after* the agent starts will be classified.

    Args:
        gmail_client: Authenticated Gmail API client.
        state_manager: State manager to read/write the history ID.
    """
    logger = logging.getLogger(__name__)
    if state_manager.get_history_id() is not None:
        logger.debug(
            "Using stored history ID: %s", state_manager.get_history_id()
        )
        return

    logger.info(
        "No stored history ID found — bootstrapping from current Gmail profile..."
    )
    profile = gmail_client.get_profile()
    history_id = str(profile["historyId"])
    state_manager.set_history_id(history_id)
    logger.info(
        "Bootstrapped history ID: %s (emails before this point will not be sorted).",
        history_id,
    )


# ------------------------------------------------------------------
# CLI helpers
# ------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="gmail-sorter",
        description="AI-powered Gmail email sorter using Claude and Google Cloud Pub/Sub.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to config.yaml (default: $CONFIG_PATH or /app/config/config.yaml).",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run the OAuth2 authorization flow and exit. "
        "Required before first normal startup.",
    )
    return parser.parse_args()


def _configure_logging(level_str: str) -> None:
    """
    Configure structured console logging.

    Args:
        level_str: Python logging level name (DEBUG, INFO, WARNING, ERROR).
    """
    level = getattr(logging, level_str, logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Suppress overly verbose third-party loggers.
    for noisy_logger in (
        "google.auth",
        "google.auth.transport",
        "googleapiclient.discovery",
        "urllib3",
        "httplib2",
    ):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


if __name__ == "__main__":
    main()
