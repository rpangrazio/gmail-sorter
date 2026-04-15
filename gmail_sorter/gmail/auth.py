"""OAuth authentication support for Gmail API access."""

from __future__ import annotations

import json
import os
from pathlib import Path

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from gmail_sorter.config.models import GmailConfig

_KEYRING_SERVICE = "gmail-sorter"
_KEYRING_ACCOUNT = "oauth-token"


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
            with token_path.open("r", encoding="utf-8") as handle:
                token_data = json.load(handle)
        except (OSError, json.JSONDecodeError):
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

        token_path = Path(self._config.token_path)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token_json, encoding="utf-8")
        os.chmod(token_path, 0o600)

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
