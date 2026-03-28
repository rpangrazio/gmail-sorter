"""
Gmail label management with in-memory caching.

Provides :class:`LabelManager`, which looks up or creates Gmail labels by name.
Labels are cached in memory to avoid redundant API calls during a session.

Nested labels (e.g., ``AI-Sorted/Work``) are created by first ensuring the
parent label (``AI-Sorted``) exists, then creating the child.
"""

import logging
from typing import Dict

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Default background and text colours used when creating new labels.
_DEFAULT_LABEL_COLOR = "#0000FF"   # Blue background
_DEFAULT_TEXT_COLOR = "#FFFFFF"    # White text


class LabelManager:
    """
    Provides ``get_or_create_label(name) → label_id`` with an in-memory cache.

    On first call for a given label name the manager fetches all existing labels
    from the Gmail API and builds the cache.  Subsequent calls for known labels
    are served from the cache without any API round-trips.

    Args:
        gmail_service: An authenticated Gmail API service resource
            (as returned by ``googleapiclient.discovery.build``).
        user_id: The Gmail user identifier.  Use ``"me"`` for the
            authenticated user.
    """

    def __init__(self, gmail_service: Resource, user_id: str = "me") -> None:
        self._service = gmail_service
        self._user_id = user_id
        # Maps label name (case-preserved) → label ID.
        self._cache: Dict[str, str] = {}
        self._cache_populated = False

    def get_or_create_label(self, name: str) -> str:
        """
        Return the Gmail label ID for *name*, creating the label if necessary.

        For nested labels (e.g., ``AI-Sorted/Work``) the parent label
        (``AI-Sorted``) is created first if it does not exist.

        Args:
            name: The full label name, e.g. ``"AI-Sorted/Work"``.

        Returns:
            The Gmail label ID string (e.g., ``"Label_12345678"``).

        Raises:
            googleapiclient.errors.HttpError: On unexpected API failures.
        """
        if not self._cache_populated:
            self._refresh_cache()

        if name in self._cache:
            return self._cache[name]

        # For nested labels ensure parent exists first.
        if "/" in name:
            parent_name = name.rsplit("/", 1)[0]
            self.get_or_create_label(parent_name)

        label_id = self._create_label(name)
        self._cache[name] = label_id
        return label_id

    def warm_cache(self, label_names: list) -> None:
        """
        Pre-create all labels in *label_names* at startup.

        Call this once during initialization to avoid per-email label creation
        latency and to surface configuration errors early.

        Args:
            label_names: List of Gmail label name strings to ensure exist.
        """
        logger.info("Warming label cache for %d labels...", len(label_names))
        for name in label_names:
            label_id = self.get_or_create_label(name)
            logger.debug("Label ready: '%s' → %s", name, label_id)
        logger.info("Label cache ready.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_cache(self) -> None:
        """Fetch all existing labels from the API and populate the cache."""
        logger.debug("Fetching existing labels from Gmail API...")
        result = (
            self._service.users()
            .labels()
            .list(userId=self._user_id)
            .execute()
        )
        for label in result.get("labels", []):
            self._cache[label["name"]] = label["id"]
        self._cache_populated = True
        logger.debug("Label cache populated with %d entries.", len(self._cache))

    def _create_label(self, name: str) -> str:
        """
        Create a new Gmail label and return its ID.

        Args:
            name: Full label name to create.

        Returns:
            The new label's ID string.
        """
        logger.info("Creating Gmail label: '%s'", name)
        try:
            result = (
                self._service.users()
                .labels()
                .create(
                    userId=self._user_id,
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                        "color": {
                            "backgroundColor": _DEFAULT_LABEL_COLOR,
                            "textColor": _DEFAULT_TEXT_COLOR,
                        },
                    },
                )
                .execute()
            )
            logger.info("Created label '%s' with ID %s", name, result["id"])
            return result["id"]
        except HttpError as exc:
            if exc.resp.status == 409:
                # Label already exists (created by a concurrent call or just
                # missed in the cache).  Refresh and try once more.
                logger.debug("Label '%s' already exists; refreshing cache.", name)
                self._cache_populated = False
                self._refresh_cache()
                if name in self._cache:
                    return self._cache[name]
            raise
