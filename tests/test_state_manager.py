"""Tests for src/state_manager.py — 100% coverage."""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.state_manager import StateManager


@pytest.fixture
def state_file(tmp_path):
    return str(tmp_path / "state.json")


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_init_no_file(state_file):
    sm = StateManager(state_file)
    assert sm.get_history_id() is None
    assert sm.get_watch_expiry() is None


def test_init_existing_file(tmp_path):
    data = {"history_id": "12345", "watch_expiry_ms": 1_711_616_400_000}
    path = tmp_path / "state.json"
    path.write_text(json.dumps(data))
    sm = StateManager(str(path))
    assert sm.get_history_id() == "12345"


def test_init_corrupt_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("this is not json {{{")
    sm = StateManager(str(path))
    assert sm.get_history_id() is None


def test_init_non_dict_json(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(["a", "list", "not", "a", "dict"]))
    sm = StateManager(str(path))
    assert sm.get_history_id() is None


# ---------------------------------------------------------------------------
# history_id
# ---------------------------------------------------------------------------

def test_get_history_id_none(state_file):
    sm = StateManager(state_file)
    assert sm.get_history_id() is None


def test_set_and_get_history_id(state_file):
    sm = StateManager(state_file)
    sm.set_history_id("99999")
    assert sm.get_history_id() == "99999"


def test_set_history_id_persisted(state_file):
    sm = StateManager(state_file)
    sm.set_history_id("persisted")
    with open(state_file) as f:
        data = json.load(f)
    assert data["history_id"] == "persisted"


def test_set_history_id_no_change_skips_write(state_file):
    sm = StateManager(state_file)
    sm.set_history_id("abc")
    mtime_after_first = os.path.getmtime(state_file)
    sm.set_history_id("abc")  # Same value — should not write
    assert sm.get_history_id() == "abc"
    # File not touched again (mtime unchanged)
    assert os.path.getmtime(state_file) == mtime_after_first


# ---------------------------------------------------------------------------
# watch_expiry
# ---------------------------------------------------------------------------

def test_get_watch_expiry_none(state_file):
    sm = StateManager(state_file)
    assert sm.get_watch_expiry() is None


def test_set_and_get_watch_expiry(state_file):
    sm = StateManager(state_file)
    now = datetime.now(tz=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    sm.set_watch_expiry(now_ms)

    expiry = sm.get_watch_expiry()
    assert expiry is not None
    assert abs(expiry.timestamp() - now.timestamp()) < 1
    assert expiry.tzinfo is not None  # UTC-aware


def test_is_watch_expiring_soon_no_expiry(state_file):
    sm = StateManager(state_file)
    assert sm.is_watch_expiring_soon() is True


def test_is_watch_expiring_soon_within_buffer(state_file):
    sm = StateManager(state_file)
    # Expiry in 1 hour — within the 24-hour default buffer
    soon_ms = int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp() * 1000)
    sm.set_watch_expiry(soon_ms)
    assert sm.is_watch_expiring_soon() is True


def test_is_watch_expiring_soon_false(state_file):
    sm = StateManager(state_file)
    # Expiry in 48 hours — outside the 24-hour buffer
    future_ms = int((datetime.now(tz=timezone.utc) + timedelta(hours=48)).timestamp() * 1000)
    sm.set_watch_expiry(future_ms)
    assert sm.is_watch_expiring_soon() is False


# ---------------------------------------------------------------------------
# Atomic write (_save)
# ---------------------------------------------------------------------------

def test_save_creates_parent_directories(tmp_path):
    nested = tmp_path / "deep" / "dir" / "state.json"
    sm = StateManager(str(nested))
    sm.set_history_id("dir-test")
    assert nested.exists()


def test_save_exception_triggers_cleanup(state_file):
    sm = StateManager(state_file)
    with patch("os.replace", side_effect=OSError("disk full")):
        with patch("os.unlink") as mock_unlink:
            with pytest.raises(OSError, match="disk full"):
                sm.set_history_id("will-fail")
            mock_unlink.assert_called_once()


def test_save_exception_unlink_also_fails(state_file):
    sm = StateManager(state_file)
    with patch("os.replace", side_effect=OSError("disk full")):
        with patch("os.unlink", side_effect=OSError("unlink failed")):
            # The original OSError should propagate
            with pytest.raises(OSError, match="disk full"):
                sm.set_history_id("will-fail")
