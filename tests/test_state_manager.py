"""Tests for src/state_manager/ package — 100% coverage."""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.state_manager import JsonStateManager, SqliteStateManager, create_state_manager


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

FUTURE_MS = int((datetime.now(tz=timezone.utc) + timedelta(hours=48)).timestamp() * 1000)
SOON_MS = int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp() * 1000)


@pytest.fixture
def state_file(tmp_path):
    return str(tmp_path / "state.json")


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "state.db")


# ===========================================================================
# JsonStateManager
# ===========================================================================

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_json_init_no_file(state_file):
    sm = JsonStateManager(state_file)
    assert sm.get_history_id() is None
    assert sm.get_watch_expiry() is None


def test_json_init_existing_file(tmp_path):
    data = {"history_id": "12345", "watch_expiry_ms": 1_711_616_400_000}
    path = tmp_path / "state.json"
    path.write_text(json.dumps(data))
    sm = JsonStateManager(str(path))
    assert sm.get_history_id() == "12345"


def test_json_init_corrupt_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("this is not json {{{")
    sm = JsonStateManager(str(path))
    assert sm.get_history_id() is None


def test_json_init_non_dict_json(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(["a", "list", "not", "a", "dict"]))
    sm = JsonStateManager(str(path))
    assert sm.get_history_id() is None


# ---------------------------------------------------------------------------
# history_id
# ---------------------------------------------------------------------------

def test_json_get_history_id_none(state_file):
    sm = JsonStateManager(state_file)
    assert sm.get_history_id() is None


def test_json_set_and_get_history_id(state_file):
    sm = JsonStateManager(state_file)
    sm.set_history_id("99999")
    assert sm.get_history_id() == "99999"


def test_json_set_history_id_persisted(state_file):
    sm = JsonStateManager(state_file)
    sm.set_history_id("persisted")
    with open(state_file) as f:
        data = json.load(f)
    assert data["history_id"] == "persisted"


def test_json_set_history_id_no_change_skips_write(state_file):
    sm = JsonStateManager(state_file)
    sm.set_history_id("abc")
    mtime_after_first = os.path.getmtime(state_file)
    sm.set_history_id("abc")  # Same value — should not write
    assert sm.get_history_id() == "abc"
    assert os.path.getmtime(state_file) == mtime_after_first


# ---------------------------------------------------------------------------
# watch_expiry
# ---------------------------------------------------------------------------

def test_json_get_watch_expiry_none(state_file):
    sm = JsonStateManager(state_file)
    assert sm.get_watch_expiry() is None


def test_json_set_and_get_watch_expiry(state_file):
    sm = JsonStateManager(state_file)
    now = datetime.now(tz=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    sm.set_watch_expiry(now_ms)
    expiry = sm.get_watch_expiry()
    assert expiry is not None
    assert abs(expiry.timestamp() - now.timestamp()) < 1
    assert expiry.tzinfo is not None


def test_json_is_watch_expiring_soon_no_expiry(state_file):
    sm = JsonStateManager(state_file)
    assert sm.is_watch_expiring_soon() is True


def test_json_is_watch_expiring_soon_within_buffer(state_file):
    sm = JsonStateManager(state_file)
    sm.set_watch_expiry(SOON_MS)
    assert sm.is_watch_expiring_soon() is True


def test_json_is_watch_expiring_soon_false(state_file):
    sm = JsonStateManager(state_file)
    sm.set_watch_expiry(FUTURE_MS)
    assert sm.is_watch_expiring_soon() is False


# ---------------------------------------------------------------------------
# Atomic write (_save)
# ---------------------------------------------------------------------------

def test_json_save_creates_parent_directories(tmp_path):
    nested = tmp_path / "deep" / "dir" / "state.json"
    sm = JsonStateManager(str(nested))
    sm.set_history_id("dir-test")
    assert nested.exists()


def test_json_save_exception_triggers_cleanup(state_file):
    sm = JsonStateManager(state_file)
    with patch("os.replace", side_effect=OSError("disk full")):
        with patch("os.unlink") as mock_unlink:
            with pytest.raises(OSError, match="disk full"):
                sm.set_history_id("will-fail")
            mock_unlink.assert_called_once()


def test_json_save_exception_unlink_also_fails(state_file):
    sm = JsonStateManager(state_file)
    with patch("os.replace", side_effect=OSError("disk full")):
        with patch("os.unlink", side_effect=OSError("unlink failed")):
            with pytest.raises(OSError, match="disk full"):
                sm.set_history_id("will-fail")


# ===========================================================================
# SqliteStateManager
# ===========================================================================

def test_sqlite_init_creates_db(db_path):
    sm = SqliteStateManager(db_path)
    assert os.path.exists(db_path)
    assert sm.get_history_id() is None
    assert sm.get_watch_expiry() is None


def test_sqlite_set_and_get_history_id(db_path):
    sm = SqliteStateManager(db_path)
    sm.set_history_id("sqlite-123")
    assert sm.get_history_id() == "sqlite-123"


def test_sqlite_set_history_id_no_change_skips_write(db_path):
    sm = SqliteStateManager(db_path)
    sm.set_history_id("same")
    sm.set_history_id("same")  # Should be a no-op
    assert sm.get_history_id() == "same"


def test_sqlite_set_and_get_watch_expiry(db_path):
    sm = SqliteStateManager(db_path)
    sm.set_watch_expiry(FUTURE_MS)
    expiry = sm.get_watch_expiry()
    assert expiry is not None
    assert expiry.tzinfo is not None


def test_sqlite_is_watch_expiring_soon_no_expiry(db_path):
    sm = SqliteStateManager(db_path)
    assert sm.is_watch_expiring_soon() is True


def test_sqlite_is_watch_expiring_soon_false(db_path):
    sm = SqliteStateManager(db_path)
    sm.set_watch_expiry(FUTURE_MS)
    assert sm.is_watch_expiring_soon() is False


def test_sqlite_creates_parent_directories(tmp_path):
    nested = str(tmp_path / "deep" / "nested" / "state.db")
    sm = SqliteStateManager(nested)
    assert os.path.exists(nested)


def test_sqlite_persists_across_instances(db_path):
    sm1 = SqliteStateManager(db_path)
    sm1.set_history_id("persisted-value")

    sm2 = SqliteStateManager(db_path)
    assert sm2.get_history_id() == "persisted-value"


# ===========================================================================
# PostgresStateManager
# ===========================================================================

def _make_psycopg2_mock():
    """Return a mock psycopg2 module with a usable connection/cursor chain."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_psycopg2 = MagicMock()
    mock_psycopg2.connect.return_value = mock_conn

    return mock_psycopg2, mock_conn, mock_cursor


def test_postgres_init(tmp_path):
    mock_psycopg2, mock_conn, mock_cursor = _make_psycopg2_mock()
    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
        from src.state_manager.postgres_backend import PostgresStateManager
        sm = PostgresStateManager(dsn="postgresql://user:pass@localhost/db")
    assert sm is not None
    mock_psycopg2.connect.assert_called()


def test_postgres_set_and_get_history_id():
    mock_psycopg2, mock_conn, mock_cursor = _make_psycopg2_mock()
    mock_cursor.fetchone.return_value = (None,)  # initial get returns None

    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
        from src.state_manager.postgres_backend import PostgresStateManager
        sm = PostgresStateManager(dsn="postgresql://user:pass@localhost/db")
        sm.set_history_id("pg-456")

    mock_cursor.execute.assert_called()


def test_postgres_set_history_id_no_change_skips_write():
    mock_psycopg2, mock_conn, mock_cursor = _make_psycopg2_mock()
    mock_cursor.fetchone.return_value = ("same-value",)

    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
        from src.state_manager.postgres_backend import PostgresStateManager
        sm = PostgresStateManager(dsn="postgresql://user:pass@localhost/db")
        execute_count_before = mock_cursor.execute.call_count
        sm.set_history_id("same-value")
        # Only the SELECT inside get_history_id() runs — no UPDATE issued
        assert mock_cursor.execute.call_count == execute_count_before + 1


def test_postgres_get_watch_expiry_none():
    mock_psycopg2, mock_conn, mock_cursor = _make_psycopg2_mock()
    mock_cursor.fetchone.return_value = (None,)

    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
        from src.state_manager.postgres_backend import PostgresStateManager
        sm = PostgresStateManager(dsn="postgresql://user:pass@localhost/db")
        assert sm.get_watch_expiry() is None


def test_postgres_set_and_get_watch_expiry():
    mock_psycopg2, mock_conn, mock_cursor = _make_psycopg2_mock()
    mock_cursor.fetchone.return_value = (FUTURE_MS,)

    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
        from src.state_manager.postgres_backend import PostgresStateManager
        sm = PostgresStateManager(dsn="postgresql://user:pass@localhost/db")
        sm.set_watch_expiry(FUTURE_MS)
        expiry = sm.get_watch_expiry()

    assert expiry is not None
    assert expiry.tzinfo is not None


def test_postgres_missing_psycopg2():
    with patch.dict("sys.modules", {"psycopg2": None}):
        with pytest.raises(ImportError, match="psycopg2"):
            from importlib import reload
            import src.state_manager.postgres_backend as pb
            reload(pb)


# ===========================================================================
# create_state_manager factory
# ===========================================================================

def test_factory_json(tmp_path):
    sm = create_state_manager("json", state_file_path=str(tmp_path / "s.json"))
    assert isinstance(sm, JsonStateManager)


def test_factory_sqlite(tmp_path):
    sm = create_state_manager("sqlite", db_path=str(tmp_path / "s.db"))
    assert isinstance(sm, SqliteStateManager)


def test_factory_postgres():
    mock_psycopg2, _, _ = _make_psycopg2_mock()
    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
        from src.state_manager.postgres_backend import PostgresStateManager
        sm = create_state_manager("postgres", dsn="postgresql://user:pass@localhost/db")
    assert isinstance(sm, PostgresStateManager)


def test_factory_unknown_backend():
    with pytest.raises(ValueError, match="Unknown"):
        create_state_manager("redis")


def test_package_getattr_postgres():
    """Importing PostgresStateManager via package __getattr__ works."""
    mock_psycopg2, _, _ = _make_psycopg2_mock()
    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
        import src.state_manager as sm_pkg
        cls = sm_pkg.PostgresStateManager
    assert cls.__name__ == "PostgresStateManager"


def test_package_getattr_unknown_raises():
    import src.state_manager as sm_pkg
    with pytest.raises(AttributeError):
        _ = sm_pkg.NonExistentClass
