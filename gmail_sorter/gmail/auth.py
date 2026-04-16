"""OAuth authentication support for Gmail API access."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

import keyring
from cryptography.fernet import Fernet, InvalidToken
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from gmail_sorter.config.models import GmailConfig

_KEYRING_SERVICE = "gmail-sorter"
_KEYRING_ACCOUNT = "oauth-token"
_KEYRING_KEY_ACCOUNT: Final[str] = "oauth-token-file-key"
_ENCRYPTED_FILE_PREFIX: Final[str] = "enc:v1:"


class GmailAuthenticator:
    """Manage Gmail OAuth credentials lifecycle and scope validation."""

    def __init__(self, config: GmailConfig) -> None:
        """Store Gmail OAuth configuration for credential operations."""

        self._config = config

    def authenticate(self) -> Credentials:
        """Run interactive OAuth flow and persist resulting credentials."""

        flow = InstalledAppFlow.from_client_secrets_file(
            self._config.credentials_path,
            scopes=self._config.scopes,
        )
        creds = flow.run_local_server(port=0)
        self.validate_scopes(creds)
        self._save_token(creds)
        return creds

    def get_credentials(self) -> Credentials:
        """Return valid credentials, refreshing or re-authenticating if required."""

        creds = self._load_token()
        if creds is None:
            return self.authenticate()

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_token(creds)

        if not creds.valid and not creds.refresh_token:
            return self.authenticate()

        self.validate_scopes(creds)
        return creds

    def _load_token(self) -> Credentials | None:
        """Load OAuth credentials from keyring or fallback token file."""

        token_json: str | None = None

        try:
            token_json = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
        except Exception:
            token_json = None

        if token_json:
            try:
                return Credentials.from_authorized_user_info(
                    json.loads(token_json),
                    scopes=self._config.scopes,
                )
            except Exception:
                token_json = None

        token_path = Path(self._config.token_path)
        if not token_path.exists():
            return None

        try:
            token_content = token_path.read_text(encoding="utf-8")
        except OSError:
            return None

        token_data = self._decode_token_payload(token_content)
        if token_data is None:
            return None

        return Credentials.from_authorized_user_info(
            token_data,
            scopes=self._config.scopes,
        )

    def _save_token(self, creds: Credentials) -> None:
        """Persist OAuth credentials to keyring and token file with safe perms."""

        token_json = creds.to_json()

        try:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, token_json)
        except Exception:
            pass

        key = self._get_or_create_file_encryption_key()
        encrypted_payload = self._encrypt_token_payload(token_json, key)

        token_path = Path(self._config.token_path)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(encrypted_payload, encoding="utf-8")
        os.chmod(token_path, 0o600)

    def _decode_token_payload(self, token_content: str) -> dict[str, object] | None:
        """Decode legacy plaintext JSON or encrypted token payload content."""

        raw_payload = token_content.strip()
        if not raw_payload:
            return None

        if raw_payload.startswith(_ENCRYPTED_FILE_PREFIX):
            encrypted_token = raw_payload[len(_ENCRYPTED_FILE_PREFIX) :]
            key = self._get_or_create_file_encryption_key()
            try:
                decrypted = Fernet(key).decrypt(encrypted_token.encode("utf-8"))
            except (InvalidToken, ValueError):
                return None
            try:
                return json.loads(decrypted.decode("utf-8"))
            except json.JSONDecodeError:
                return None

        try:
            return json.loads(raw_payload)
        except json.JSONDecodeError:
            return None

    def _encrypt_token_payload(self, token_json: str, key: bytes) -> str:
        """Encrypt token JSON for at-rest file storage."""

        encrypted = Fernet(key).encrypt(token_json.encode("utf-8"))
        return f"{_ENCRYPTED_FILE_PREFIX}{encrypted.decode('utf-8')}"

    def _get_or_create_file_encryption_key(self) -> bytes:
        """Load encryption key from keyring or deterministic local key file."""

        key_value = self._read_key_from_keyring()
        if key_value:
            return key_value

        generated_key = Fernet.generate_key()
        if self._write_key_to_keyring(generated_key.decode("utf-8")):
            return generated_key

        key_path = self._token_key_path()
        if key_path.exists():
            try:
                existing_key = key_path.read_text(encoding="utf-8").strip().encode("utf-8")
                Fernet(existing_key)
                return existing_key
            except (OSError, ValueError):
                pass

        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(generated_key.decode("utf-8"), encoding="utf-8")
        os.chmod(key_path, 0o600)
        return generated_key

    def _read_key_from_keyring(self) -> bytes | None:
        """Read token-file encryption key from keyring if available."""

        try:
            key = keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY_ACCOUNT)
        except Exception:
            return None

        if not key:
            return None

        try:
            encoded = key.encode("utf-8")
            Fernet(encoded)
            return encoded
        except ValueError:
            return None

    def _write_key_to_keyring(self, key: str) -> bool:
        """Persist token-file encryption key to keyring."""

        try:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY_ACCOUNT, key)
        except Exception:
            return False
        return True

    def _token_key_path(self) -> Path:
        """Return deterministic local path for token-file encryption key."""

        token_path = Path(self._config.token_path)
        return token_path.with_suffix(f"{token_path.suffix}.key")

    def validate_scopes(self, creds: Credentials) -> None:
        """Validate required Gmail scopes are present on credentials."""

        granted_scopes = set(creds.scopes or [])
        required_scopes = set(self._config.scopes)
        missing_scopes = sorted(required_scopes - granted_scopes)

        if missing_scopes:
            missing = ", ".join(missing_scopes)
            raise SystemExit(
                "Missing required OAuth scopes. "
                f"Re-run authentication with these scopes: {missing}"
            )
