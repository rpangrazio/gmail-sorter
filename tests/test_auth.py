"""Tests for src/auth.py — 100% coverage."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from src.auth import GoogleAuthManager, REQUIRED_SCOPES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_valid_creds():
    creds = MagicMock(spec=Credentials)
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "rt"
    creds.to_json.return_value = '{"token": "valid"}'
    return creds


def make_expired_creds():
    creds = MagicMock(spec=Credentials)
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "rt"
    creds.to_json.return_value = '{"token": "refreshed"}'
    return creds


@pytest.fixture
def auth(tmp_path):
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text('{"installed": {}}')
    token_path = tmp_path / "token.json"
    return GoogleAuthManager(str(creds_path), str(token_path))


# ---------------------------------------------------------------------------
# get_credentials
# ---------------------------------------------------------------------------

def test_get_credentials_returns_cached_valid(auth):
    creds = make_valid_creds()
    auth._cached = creds
    assert auth.get_credentials() is creds


def test_get_credentials_refreshes_expired_token(auth):
    creds = make_expired_creds()
    with patch("src.auth.Credentials.from_authorized_user_file", return_value=creds):
        auth._token_path.write_text('{"token": "old"}')
        with patch.object(creds, "refresh") as mock_refresh:
            result = auth.get_credentials()
    mock_refresh.assert_called_once()
    assert result is creds
    # Token should be saved after refresh
    assert auth._token_path.exists()


def test_get_credentials_refresh_fails_runs_flow(auth):
    creds = make_expired_creds()
    fresh = make_valid_creds()
    fresh.to_json.return_value = '{"fresh": true}'

    with patch("src.auth.Credentials.from_authorized_user_file", return_value=creds):
        auth._token_path.write_text('{"token": "old"}')
        with patch.object(creds, "refresh", side_effect=RefreshError("revoked")):
            with patch.object(auth, "_run_oauth_flow", return_value=fresh):
                result = auth.get_credentials()

    assert result is fresh


def test_get_credentials_no_stored_token_runs_flow(auth):
    fresh = make_valid_creds()
    with patch.object(auth, "_run_oauth_flow", return_value=fresh):
        result = auth.get_credentials()
    assert result is fresh


def test_get_credentials_caches_result(auth):
    fresh = make_valid_creds()
    with patch.object(auth, "_run_oauth_flow", return_value=fresh):
        auth.get_credentials()
    assert auth._cached is fresh


# ---------------------------------------------------------------------------
# _load_token
# ---------------------------------------------------------------------------

def test_load_token_no_file(auth):
    assert auth._load_token() is None


def test_load_token_success(auth):
    creds = make_valid_creds()
    auth._token_path.write_text('{"token": "data"}')
    with patch("src.auth.Credentials.from_authorized_user_file", return_value=creds):
        result = auth._load_token()
    assert result is creds


def test_load_token_load_error(auth):
    auth._token_path.write_text('{}')
    with patch(
        "src.auth.Credentials.from_authorized_user_file",
        side_effect=Exception("corrupt"),
    ):
        result = auth._load_token()
    assert result is None


# ---------------------------------------------------------------------------
# _save_token
# ---------------------------------------------------------------------------

def test_save_token_writes_file(auth):
    creds = make_valid_creds()
    creds.to_json.return_value = '{"token": "saved"}'
    auth._save_token(creds)
    assert auth._token_path.read_text() == '{"token": "saved"}'


def test_save_token_creates_parent_directory(tmp_path):
    creds_path = tmp_path / "creds.json"
    creds_path.write_text("{}")
    token_path = tmp_path / "sub" / "token.json"
    manager = GoogleAuthManager(str(creds_path), str(token_path))
    creds = make_valid_creds()
    creds.to_json.return_value = '{"token": "new"}'
    manager._save_token(creds)
    assert token_path.exists()


# ---------------------------------------------------------------------------
# _run_oauth_flow
# ---------------------------------------------------------------------------

def test_run_oauth_flow_missing_credentials_file(tmp_path):
    manager = GoogleAuthManager(
        credentials_path=str(tmp_path / "missing.json"),
        token_path=str(tmp_path / "token.json"),
    )
    with pytest.raises(FileNotFoundError, match="not found"):
        manager._run_oauth_flow()


def test_run_oauth_flow_browser_success(auth):
    creds = make_valid_creds()
    creds.to_json.return_value = '{"oauth": "done"}'
    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = creds

    with patch("src.auth.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow):
        result = auth._run_oauth_flow()

    assert result is creds
    mock_flow.run_local_server.assert_called_once()


def test_run_oauth_flow_browser_fails_uses_console(auth):
    creds = make_valid_creds()
    creds.to_json.return_value = '{"oauth": "console"}'
    mock_flow = MagicMock()
    mock_flow.run_local_server.side_effect = Exception("no browser")
    mock_flow.run_console.return_value = creds

    with patch("src.auth.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow):
        result = auth._run_oauth_flow()

    assert result is creds
    mock_flow.run_console.assert_called_once()
