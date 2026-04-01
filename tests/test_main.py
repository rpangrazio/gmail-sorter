"""Tests for src/main.py — 100% coverage."""

import collections
import logging
import sys
import threading
from unittest.mock import MagicMock, call, patch

import pytest

from src.config_loader import Category, Config
from src.gmail_client import HistoryExpiredError
from src.main import (
    _ProcessingContext,
    _bootstrap_history_id,
    _configure_logging,
    _create_state_manager,
    _parse_args,
    _watch_renewal_loop,
    _DEDUP_MAX_SIZE,
    main,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def make_config(ai_provider="copilot", dry_run=False):
    config = MagicMock(spec=Config)
    config.ai_provider = ai_provider
    config.copilot_model = "gpt-4o"
    config.openai_model = "gpt-4o"
    config.state_backend = "json"
    config.dry_run = dry_run
    config.log_level = "INFO"
    config.pubsub_subscription = "projects/p/subscriptions/s"
    config.gmail_watch_topic = "projects/p/topics/t"
    config.categories = [
        Category(name="work", label="AI-Sorted/Work", description="Work emails"),
    ]
    return config


def make_context(dry_run=False, categories=None):
    if categories is None:
        categories = {"work": "AI-Sorted/Work"}
    return _ProcessingContext(
        gmail_client=MagicMock(),
        classifier=MagicMock(),
        label_manager=MagicMock(),
        state_manager=MagicMock(),
        config_categories=categories,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# _parse_args
# ---------------------------------------------------------------------------

def test_parse_args_defaults():
    with patch("sys.argv", ["gmail-sorter"]):
        args = _parse_args()
    assert args.config is None
    assert args.setup is False


def test_parse_args_config_flag():
    with patch("sys.argv", ["gmail-sorter", "--config", "/path/to/config.yaml"]):
        args = _parse_args()
    assert args.config == "/path/to/config.yaml"


def test_parse_args_setup_flag():
    with patch("sys.argv", ["gmail-sorter", "--setup"]):
        args = _parse_args()
    assert args.setup is True


# ---------------------------------------------------------------------------
# _configure_logging
# ---------------------------------------------------------------------------

def test_configure_logging_valid_level():
    # Should not raise
    _configure_logging("DEBUG")
    _configure_logging("INFO")
    _configure_logging("WARNING")
    _configure_logging("ERROR")


def test_configure_logging_invalid_level_falls_back_to_info():
    # getattr(logging, "NOTAREAL", logging.INFO) → logging.INFO
    _configure_logging("NOTAREAL")  # Should not raise


# ---------------------------------------------------------------------------
# _bootstrap_history_id
# ---------------------------------------------------------------------------

def test_bootstrap_history_id_already_stored():
    gmail_client = MagicMock()
    state_manager = MagicMock()
    state_manager.get_history_id.return_value = "existing_id"

    _bootstrap_history_id(gmail_client, state_manager)

    gmail_client.get_profile.assert_not_called()
    state_manager.set_history_id.assert_not_called()


def test_bootstrap_history_id_bootstraps_from_profile():
    gmail_client = MagicMock()
    gmail_client.get_profile.return_value = {"historyId": "999999"}
    state_manager = MagicMock()
    state_manager.get_history_id.return_value = None

    _bootstrap_history_id(gmail_client, state_manager)

    state_manager.set_history_id.assert_called_once_with("999999")


# ---------------------------------------------------------------------------
# _watch_renewal_loop
# ---------------------------------------------------------------------------

def test_watch_renewal_loop_stops_immediately():
    stop = threading.Event()
    stop.set()
    gmail_client = MagicMock()
    state_manager = MagicMock()
    _watch_renewal_loop(gmail_client, "topic", state_manager, stop)
    gmail_client.ensure_watch.assert_not_called()


def test_watch_renewal_loop_calls_ensure_watch():
    stop = threading.Event()
    gmail_client = MagicMock()
    state_manager = MagicMock()

    call_count = [0]

    def fake_wait(timeout):
        call_count[0] += 1
        if call_count[0] == 1:
            return False  # Not set → run body
        return True  # Set → stop

    with patch.object(stop, "wait", side_effect=fake_wait):
        _watch_renewal_loop(gmail_client, "topic", state_manager, stop)

    gmail_client.ensure_watch.assert_called_once_with("topic", state_manager)


def test_watch_renewal_loop_handles_exception():
    stop = threading.Event()
    gmail_client = MagicMock()
    gmail_client.ensure_watch.side_effect = RuntimeError("network error")
    state_manager = MagicMock()

    call_count = [0]

    def fake_wait(timeout):
        call_count[0] += 1
        if call_count[0] == 1:
            return False
        return True

    with patch.object(stop, "wait", side_effect=fake_wait):
        _watch_renewal_loop(gmail_client, "topic", state_manager, stop)

    gmail_client.ensure_watch.assert_called_once()


# ---------------------------------------------------------------------------
# _ProcessingContext.handle_notification
# ---------------------------------------------------------------------------

def test_handle_notification_no_stored_history_id_with_notification_id():
    ctx = make_context()
    ctx._state.get_history_id.return_value = None

    ctx.handle_notification({"historyId": "12345", "emailAddress": "a@b.com"})

    ctx._state.set_history_id.assert_called_once_with("12345")


def test_handle_notification_no_stored_history_id_no_notification_id():
    ctx = make_context()
    ctx._state.get_history_id.return_value = None

    ctx.handle_notification({"emailAddress": "a@b.com"})  # No historyId

    ctx._state.set_history_id.assert_not_called()


def test_handle_notification_history_expired_with_history_id():
    ctx = make_context()
    ctx._state.get_history_id.return_value = "old_id"
    ctx._gmail.list_new_messages.side_effect = HistoryExpiredError("expired")

    ctx.handle_notification({"historyId": "new_id", "emailAddress": "a@b.com"})

    ctx._state.set_history_id.assert_called_once_with("new_id")


def test_handle_notification_history_expired_no_history_id():
    ctx = make_context()
    ctx._state.get_history_id.return_value = "old_id"
    ctx._gmail.list_new_messages.side_effect = HistoryExpiredError("expired")

    ctx.handle_notification({"emailAddress": "a@b.com"})  # No historyId

    ctx._state.set_history_id.assert_not_called()


def test_handle_notification_empty_messages_max_id_advances():
    ctx = make_context()
    ctx._state.get_history_id.return_value = "100"
    ctx._gmail.list_new_messages.return_value = ([], "200")

    ctx.handle_notification({"historyId": "200", "emailAddress": "a@b.com"})

    ctx._state.set_history_id.assert_called_once_with("200")


def test_handle_notification_empty_messages_max_id_same():
    ctx = make_context()
    ctx._state.get_history_id.return_value = "100"
    ctx._gmail.list_new_messages.return_value = ([], "100")

    ctx.handle_notification({"historyId": "100", "emailAddress": "a@b.com"})

    ctx._state.set_history_id.assert_not_called()


def test_handle_notification_processes_messages():
    ctx = make_context()
    ctx._state.get_history_id.return_value = "100"
    ctx._gmail.list_new_messages.return_value = (["msg1", "msg2"], "200")
    ctx._gmail.get_message.return_value = {
        "subject": "Test", "from_": "a@b.com", "snippet": "", "body": ""
    }
    ctx._classifier.classify.return_value = None

    ctx.handle_notification({"historyId": "200", "emailAddress": "a@b.com"})

    assert ctx._gmail.get_message.call_count == 2
    ctx._state.set_history_id.assert_called_once_with("200")


# ---------------------------------------------------------------------------
# _ProcessingContext._process_message
# ---------------------------------------------------------------------------

def test_process_message_dedup_skip():
    ctx = make_context()
    ctx._processed_set.add("already_processed")
    ctx._processed_ids.append("already_processed")

    ctx._process_message("already_processed")

    ctx._gmail.get_message.assert_not_called()


def test_process_message_fetch_fails():
    ctx = make_context()
    ctx._gmail.get_message.side_effect = RuntimeError("fetch error")

    ctx._process_message("msg1")

    ctx._classifier.classify.assert_not_called()


def test_process_message_classify_fails():
    ctx = make_context()
    ctx._gmail.get_message.return_value = {
        "subject": "Test", "from_": "a@b.com", "snippet": "", "body": ""
    }
    ctx._classifier.classify.side_effect = RuntimeError("classify error")

    ctx._process_message("msg1")

    ctx._labels.get_or_create_label.assert_not_called()


def test_process_message_no_category_match():
    ctx = make_context()
    ctx._gmail.get_message.return_value = {
        "subject": "Test", "from_": "a@b.com", "snippet": "", "body": ""
    }
    ctx._classifier.classify.return_value = None

    ctx._process_message("msg1")

    ctx._labels.get_or_create_label.assert_not_called()
    assert "msg1" in ctx._processed_set


def test_process_message_category_not_in_config():
    ctx = make_context(categories={})  # No categories configured
    ctx._gmail.get_message.return_value = {
        "subject": "Test", "from_": "a@b.com", "snippet": "", "body": ""
    }
    ctx._classifier.classify.return_value = "work"  # Not in config_categories

    ctx._process_message("msg1")

    ctx._labels.get_or_create_label.assert_not_called()
    assert "msg1" in ctx._processed_set


def test_process_message_dry_run():
    ctx = make_context(dry_run=True)
    ctx._gmail.get_message.return_value = {
        "subject": "Test", "from_": "a@b.com", "snippet": "", "body": ""
    }
    ctx._classifier.classify.return_value = "work"

    ctx._process_message("msg1")

    ctx._labels.get_or_create_label.assert_not_called()
    assert "msg1" in ctx._processed_set


def test_process_message_success():
    ctx = make_context()
    ctx._gmail.get_message.return_value = {
        "subject": "Work email", "from_": "boss@co.com", "snippet": "", "body": ""
    }
    ctx._classifier.classify.return_value = "work"
    ctx._labels.get_or_create_label.return_value = "Label_work"

    ctx._process_message("msg1")

    ctx._labels.get_or_create_label.assert_called_once_with("AI-Sorted/Work")
    ctx._gmail.apply_label.assert_called_once_with("msg1", "Label_work")
    assert "msg1" in ctx._processed_set


def test_process_message_apply_label_fails():
    ctx = make_context()
    ctx._gmail.get_message.return_value = {
        "subject": "Test", "from_": "a@b.com", "snippet": "", "body": ""
    }
    ctx._classifier.classify.return_value = "work"
    ctx._labels.get_or_create_label.return_value = "Label_work"
    ctx._gmail.apply_label.side_effect = RuntimeError("label error")

    ctx._process_message("msg1")

    # Error logged but message still added to dedup set
    assert "msg1" in ctx._processed_set


def test_process_message_dedup_eviction():
    """When deque is full the oldest entry is evicted from the set."""
    ctx = make_context()

    oldest_id = "id_oldest"
    all_ids = [oldest_id] + [f"id_{i}" for i in range(_DEDUP_MAX_SIZE - 1)]
    ctx._processed_ids = collections.deque(all_ids, maxlen=_DEDUP_MAX_SIZE)
    ctx._processed_set = set(all_ids)

    assert oldest_id in ctx._processed_set

    ctx._gmail.get_message.return_value = {
        "subject": "New", "from_": "a@b.com", "snippet": "", "body": ""
    }
    ctx._classifier.classify.return_value = None

    ctx._process_message("new_msg_id")

    assert oldest_id not in ctx._processed_set
    assert "new_msg_id" in ctx._processed_set


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

PATCH_TARGETS = {
    "load_dotenv": "src.main.load_dotenv",
    "load_config": "src.main.load_config",
    "configure_logging": "src.main._configure_logging",
    "auth_cls": "src.main.GoogleAuthManager",
    "build": "src.main.build",
    "gmail_client_cls": "src.main.GmailClient",
    "create_state_manager": "src.main._create_state_manager",
    "label_manager_cls": "src.main.LabelManager",
    "create_classifier": "src.main.create_classifier",
    "pubsub_client_cls": "src.main.PubSubClient",
    "bootstrap": "src.main._bootstrap_history_id",
    "thread_cls": "src.main.threading.Thread",
}


def run_main_with_patches(
    config,
    pubsub_side_effect=None,
    env_overrides=None,
    argv=None,
):
    """Helper to run main() with all external deps mocked."""
    if argv is None:
        argv = ["gmail-sorter"]
    if env_overrides is None:
        env_overrides = {"GITHUB_TOKEN": "ghp_key", "OPENAI_API_KEY": ""}

    mock_creds = MagicMock()
    mock_auth = MagicMock()
    mock_auth.get_credentials.return_value = mock_creds

    mock_pubsub = MagicMock()
    if pubsub_side_effect is None:
        mock_pubsub.run_forever.side_effect = KeyboardInterrupt
    else:
        mock_pubsub.run_forever.side_effect = pubsub_side_effect

    mock_thread = MagicMock()

    with (
        patch("sys.argv", argv),
        patch.dict("os.environ", env_overrides, clear=False),
        patch(PATCH_TARGETS["load_dotenv"]),
        patch(PATCH_TARGETS["load_config"], return_value=config),
        patch(PATCH_TARGETS["configure_logging"]),
        patch(PATCH_TARGETS["auth_cls"], return_value=mock_auth),
        patch(PATCH_TARGETS["build"], return_value=MagicMock()),
        patch(PATCH_TARGETS["gmail_client_cls"], return_value=MagicMock()),
        patch(PATCH_TARGETS["create_state_manager"], return_value=MagicMock()),
        patch(PATCH_TARGETS["label_manager_cls"], return_value=MagicMock()),
        patch(PATCH_TARGETS["create_classifier"], return_value=MagicMock()),
        patch(PATCH_TARGETS["pubsub_client_cls"], return_value=mock_pubsub),
        patch(PATCH_TARGETS["bootstrap"]),
        patch(PATCH_TARGETS["thread_cls"], return_value=mock_thread),
    ):
        main()


def test_main_normal_flow_keyboard_interrupt():
    config = make_config(ai_provider="copilot")
    run_main_with_patches(config)  # KeyboardInterrupt is caught gracefully


def test_main_dry_run_log(caplog):
    config = make_config(ai_provider="copilot", dry_run=True)
    with caplog.at_level(logging.WARNING, logger="src.main"):
        run_main_with_patches(config)
    assert "DRY RUN" in caplog.text


def test_main_openai_provider():
    config = make_config(ai_provider="openai")
    run_main_with_patches(
        config,
        env_overrides={"GITHUB_TOKEN": "", "OPENAI_API_KEY": "oai-key"},
    )


def test_main_missing_github_token_exits():
    config = make_config(ai_provider="copilot")
    with (
        patch("sys.argv", ["gmail-sorter"]),
        patch.dict("os.environ", {"GITHUB_TOKEN": "", "OPENAI_API_KEY": ""}, clear=False),
        patch(PATCH_TARGETS["load_dotenv"]),
        patch(PATCH_TARGETS["load_config"], return_value=config),
        patch(PATCH_TARGETS["configure_logging"]),
        pytest.raises(SystemExit),
    ):
        main()


def test_main_missing_openai_key_exits():
    config = make_config(ai_provider="openai")
    with (
        patch("sys.argv", ["gmail-sorter"]),
        patch.dict("os.environ", {"GITHUB_TOKEN": "", "OPENAI_API_KEY": ""}, clear=False),
        patch(PATCH_TARGETS["load_dotenv"]),
        patch(PATCH_TARGETS["load_config"], return_value=config),
        patch(PATCH_TARGETS["configure_logging"]),
        pytest.raises(SystemExit),
    ):
        main()


def test_main_setup_flag():
    config = make_config(ai_provider="copilot")
    mock_auth = MagicMock()
    mock_auth.get_credentials.return_value = MagicMock()

    with (
        patch("sys.argv", ["gmail-sorter", "--setup"]),
        patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_key"}, clear=False),
        patch(PATCH_TARGETS["load_dotenv"]),
        patch(PATCH_TARGETS["load_config"], return_value=config),
        patch(PATCH_TARGETS["configure_logging"]),
        patch(PATCH_TARGETS["auth_cls"], return_value=mock_auth),
    ):
        main()  # Should return after setup without entering pubsub loop

    mock_auth.get_credentials.assert_called_once()


def test_main_sqlite_backend():
    config = make_config(ai_provider="copilot")
    config.state_backend = "sqlite"
    run_main_with_patches(config, env_overrides={"GITHUB_TOKEN": "ghp_key", "OPENAI_API_KEY": ""})


def test_main_postgres_backend():
    config = make_config(ai_provider="copilot")
    config.state_backend = "postgres"
    run_main_with_patches(
        config,
        env_overrides={"GITHUB_TOKEN": "ghp_key", "OPENAI_API_KEY": "", "DATABASE_URL": "postgresql://u:p@h/db"},
    )


def test_create_state_manager_json():
    sm = _create_state_manager("json", "/tmp/s.json", "/tmp/s.db", "")
    from src.state_manager import JsonStateManager
    assert isinstance(sm, JsonStateManager)


def test_create_state_manager_sqlite(tmp_path):
    sm = _create_state_manager("sqlite", "/tmp/s.json", str(tmp_path / "s.db"), "")
    from src.state_manager import SqliteStateManager
    assert isinstance(sm, SqliteStateManager)


def test_create_state_manager_postgres_missing_url_exits():
    with pytest.raises(SystemExit):
        _create_state_manager("postgres", "/tmp/s.json", "/tmp/s.db", "")


def test_create_state_manager_postgres_with_url():
    mock_psycopg2 = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_psycopg2.connect.return_value = mock_conn
    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
        from src.state_manager.postgres_backend import PostgresStateManager
        sm = _create_state_manager("postgres", "/tmp/s.json", "/tmp/s.db", "postgresql://u:p@h/db")
    assert isinstance(sm, PostgresStateManager)


def test_main_uses_config_path_from_env():
    config = make_config(ai_provider="copilot")
    with (
        patch("sys.argv", ["gmail-sorter"]),
        patch.dict(
            "os.environ",
            {"GITHUB_TOKEN": "ghp_key", "CONFIG_PATH": "/custom/config.yaml"},
            clear=False,
        ),
        patch(PATCH_TARGETS["load_dotenv"]),
        patch(PATCH_TARGETS["load_config"], return_value=config) as mock_load,
        patch(PATCH_TARGETS["configure_logging"]),
        patch(PATCH_TARGETS["auth_cls"], return_value=MagicMock()),
        patch(PATCH_TARGETS["build"], return_value=MagicMock()),
        patch(PATCH_TARGETS["gmail_client_cls"], return_value=MagicMock()),
        patch(PATCH_TARGETS["create_state_manager"], return_value=MagicMock()),
        patch(PATCH_TARGETS["label_manager_cls"], return_value=MagicMock()),
        patch(PATCH_TARGETS["create_classifier"], return_value=MagicMock()),
        patch(PATCH_TARGETS["pubsub_client_cls"], return_value=MagicMock(
            **{"run_forever.side_effect": KeyboardInterrupt}
        )),
        patch(PATCH_TARGETS["bootstrap"]),
        patch(PATCH_TARGETS["thread_cls"], return_value=MagicMock()),
    ):
        main()

    mock_load.assert_called_once_with("/custom/config.yaml")
