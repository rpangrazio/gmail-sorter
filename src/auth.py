"""
Google OAuth2 authentication manager.

Handles the full OAuth2 lifecycle: initial interactive authorization,
token persistence to disk, and automatic token refresh on expiry.

The same credentials are used for both the Gmail API and the Cloud Pub/Sub API,
which is the appropriate approach for a single-user personal agent.
"""

import logging
from pathlib import Path
from typing import List, Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

# Scopes required by the application:
#   - gmail.modify  : read messages, add/remove labels, watch inbox
#   - pubsub        : pull messages from Pub/Sub subscriptions
REQUIRED_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/pubsub",
]


class GoogleAuthManager:
    """
    Manages Google OAuth2 credentials with automatic refresh and persistence.

    Usage::

        auth = GoogleAuthManager(
            credentials_path="/credentials/credentials.json",
            token_path="/data/token.json",
        )
        creds = auth.get_credentials()
        # Pass creds to googleapiclient.discovery.build() or pubsub clients
    """

    def __init__(self, credentials_path: str, token_path: str) -> None:
        """
        Initialize the auth manager.

        Args:
            credentials_path: Path to the OAuth2 client secrets JSON file
                downloaded from Google Cloud Console.
            token_path: Path where the user's OAuth2 token will be stored
                (created automatically after first authorization).
        """
        self._credentials_path = Path(credentials_path)
        self._token_path = Path(token_path)
        self._cached: Optional[Credentials] = None

    def get_credentials(self) -> Credentials:
        """
        Return valid Google credentials, refreshing or re-authorizing as needed.

        On first call (or when the stored token is missing/invalid), opens a
        browser-based OAuth2 consent flow.  Subsequent calls return the cached
        or refreshed credentials without user interaction.

        Returns:
            A valid :class:`google.oauth2.credentials.Credentials` instance.

        Raises:
            FileNotFoundError: If *credentials_path* does not exist.
            google.auth.exceptions.RefreshError: If the refresh token is revoked
                and re-authorization is required.
        """
        if self._cached and self._cached.valid:
            return self._cached

        creds = self._load_token()

        if creds and creds.expired and creds.refresh_token:
            logger.info("Access token expired — refreshing via refresh token...")
            try:
                creds.refresh(Request())
                self._save_token(creds)
                logger.info("Token refreshed successfully.")
            except RefreshError as exc:
                logger.warning(
                    "Token refresh failed (%s). Re-authorization required.", exc
                )
                creds = None

        if not creds:
            creds = self._run_oauth_flow()

        self._cached = creds
        return creds

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_token(self) -> Optional[Credentials]:
        """Load previously stored credentials from disk."""
        if not self._token_path.exists():
            logger.debug("No stored token found at %s.", self._token_path)
            return None

        logger.debug("Loading stored token from %s.", self._token_path)
        try:
            return Credentials.from_authorized_user_file(
                str(self._token_path), REQUIRED_SCOPES
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load stored token: %s", exc)
            return None

    def _save_token(self, creds: Credentials) -> None:
        """Persist credentials to disk so they survive container restarts."""
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())
        logger.debug("Token saved to %s.", self._token_path)

    def _run_oauth_flow(self) -> Credentials:
        """
        Run the interactive OAuth2 consent flow.

        Attempts to open a local browser window; if that is unavailable
        (e.g., headless Docker container) falls back to a console-based URL
        prompt that the user can open on another device.

        Returns:
            Fresh :class:`google.oauth2.credentials.Credentials`.

        Raises:
            FileNotFoundError: If the client secrets file is missing.
        """
        if not self._credentials_path.exists():
            raise FileNotFoundError(
                f"OAuth2 client secrets file not found: {self._credentials_path}\n"
                "1. Go to Google Cloud Console → APIs & Services → Credentials.\n"
                "2. Create an OAuth 2.0 Client ID (Desktop App type).\n"
                "3. Download the JSON and place it at the path above.\n"
                "Then re-run with --setup."
            )

        logger.info(
            "Starting OAuth2 authorization flow. "
            "A browser window will open (or a URL will be printed if headless)."
        )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self._credentials_path), REQUIRED_SCOPES
        )

        # Try browser-based flow first; fall back to console prompt.
        try:
            creds = flow.run_local_server(port=0, open_browser=True)
        except Exception:  # noqa: BLE001
            logger.info(
                "Browser flow unavailable — falling back to console-based authorization."
            )
            creds = flow.run_console()

        self._save_token(creds)
        logger.info("OAuth2 authorization complete. Token stored at %s.", self._token_path)
        return creds
