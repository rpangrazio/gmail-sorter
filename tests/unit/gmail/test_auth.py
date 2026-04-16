"""Unit tests for Gmail OAuth authenticator behavior."""

from __future__ import annotations

import json
from pathlib import Path
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


def test_save_token_writes_encrypted_fallback_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Token fallback file should be encrypted and non-JSON plaintext."""

    config = build_config()
    config.token_path = str(tmp_path / "token.json")
    authenticator = GmailAuthenticator(config)

    creds = Mock()
    creds.to_json.return_value = json.dumps(
        {
            "token": "abc",
            "refresh_token": "ref",
            "client_id": "id",
            "client_secret": "secret",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )

    monkeypatch.setattr(
        "gmail_sorter.gmail.auth.keyring.set_password",
        lambda *_: (_ for _ in ()).throw(RuntimeError("keyring down")),
    )
    monkeypatch.setattr("gmail_sorter.gmail.auth.keyring.get_password", lambda *_: None)

    authenticator._save_token(creds)

    token_path = Path(config.token_path)
    content = token_path.read_text(encoding="utf-8")
    assert content.startswith("enc:v1:")
    assert not content.strip().startswith("{")


def test_load_token_supports_legacy_plaintext_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Authenticator should still read legacy plaintext token files."""

    config = build_config()
    config.token_path = str(tmp_path / "token.json")
    authenticator = GmailAuthenticator(config)

    plaintext = {
        "token": "legacy-token",
        "refresh_token": "legacy-refresh",
        "client_id": "legacy-id",
        "client_secret": "legacy-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    Path(config.token_path).write_text(json.dumps(plaintext), encoding="utf-8")
    monkeypatch.setattr("gmail_sorter.gmail.auth.keyring.get_password", lambda *_: None)

    loaded = authenticator._load_token()

    assert loaded is not None
    assert getattr(loaded, "refresh_token", None) == "legacy-refresh"


def test_load_token_reads_encrypted_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Authenticator should decrypt encrypted token payloads from disk."""

    config = build_config()
    config.token_path = str(tmp_path / "token.json")
    authenticator = GmailAuthenticator(config)

    payload = {
        "token": "enc-token",
        "refresh_token": "enc-refresh",
        "client_id": "enc-id",
        "client_secret": "enc-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    monkeypatch.setattr(
        "gmail_sorter.gmail.auth.keyring.get_password",
        lambda service, account: None,
    )
    monkeypatch.setattr(
        "gmail_sorter.gmail.auth.keyring.set_password",
        lambda *_: (_ for _ in ()).throw(RuntimeError("keyring down")),
    )

    encoded = authenticator._encrypt_token_payload(
        json.dumps(payload),
        authenticator._get_or_create_file_encryption_key(),
    )
    Path(config.token_path).write_text(encoded, encoding="utf-8")

    loaded = authenticator._load_token()

    assert loaded is not None
    assert getattr(loaded, "refresh_token", None) == "enc-refresh"
