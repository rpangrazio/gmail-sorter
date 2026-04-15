"""Unit tests for Gmail OAuth authenticator behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from gmail_sorter.config.models import GmailConfig
from gmail_sorter.gmail.auth import GmailAuthenticator


def build_config() -> GmailConfig:
    """Return a GmailConfig fixture for authenticator tests."""

    return GmailConfig(
        credentials_path="./credentials.json",
        token_path="./token.json",
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        ],
    )


def test_save_token_sets_restricted_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Saving tokens should set file mode 0600 on the token path."""

    authenticator = GmailAuthenticator(build_config())
    creds = Mock()
    creds.to_json.return_value = "{}"

    chmod_calls: list[tuple[object, int]] = []

    def fake_chmod(path: object, mode: int) -> None:
        chmod_calls.append((path, mode))

    monkeypatch.setattr("gmail_sorter.gmail.auth.os.chmod", fake_chmod)
    monkeypatch.setattr("gmail_sorter.gmail.auth.keyring.set_password", lambda *_: None)

    authenticator._save_token(creds)

    assert chmod_calls
    assert chmod_calls[-1][1] == 0o600


def test_get_credentials_refreshes_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expired credentials with refresh tokens should be refreshed."""

    authenticator = GmailAuthenticator(build_config())

    creds = SimpleNamespace(
        expired=True,
        refresh_token="refresh-token",
        valid=True,
        scopes=build_config().scopes,
        refresh=Mock(),
    )

    monkeypatch.setattr(authenticator, "_load_token", lambda: creds)
    monkeypatch.setattr(authenticator, "_save_token", lambda _creds: None)

    loaded = authenticator.get_credentials()

    assert loaded is creds
    assert creds.refresh.call_count == 1


def test_validate_scopes_raises_on_missing_scope() -> None:
    """Scope validation exits when required scopes are absent."""

    authenticator = GmailAuthenticator(build_config())
    creds = SimpleNamespace(scopes=["https://www.googleapis.com/auth/gmail.readonly"])

    with pytest.raises(SystemExit):
        authenticator.validate_scopes(creds)
