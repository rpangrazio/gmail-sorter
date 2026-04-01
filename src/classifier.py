"""
AI-powered email classifier with pluggable provider backends.

Supports two classification backends, selected via ``ai_provider`` in config:

- **copilot** (default): Uses GitHub Copilot's OpenAI-compatible chat-completion
  API at ``https://api.githubcopilot.com``.  Requires a GitHub personal access
  token (``GITHUB_TOKEN``) with Copilot access.

- **openai**: Uses any OpenAI chat-completion model (default ``gpt-4o``).
  Pass ``OPENAI_API_KEY`` and optionally ``OPENAI_BASE_URL`` to point at a
  compatible third-party API endpoint.

Public interface — call :func:`create_classifier` to obtain the right backend::

    classifier = create_classifier(config, github_token="...", openai_api_key="...")
    category = classifier.classify(email_data)
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.config_loader import Category, Config

logger = logging.getLogger(__name__)

# Default models per provider.
_DEFAULT_COPILOT_MODEL = "gpt-4o"
_DEFAULT_OPENAI_MODEL = "gpt-4o"

# Maximum tokens allocated for the classification response.
# The answer is a single category name, so this is intentionally small.
_MAX_TOKENS = 256


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseClassifier(ABC):
    """
    Abstract base class for email classifiers.

    Concrete subclasses implement :meth:`classify` for a specific AI provider.
    All subclasses share the same prompt-building helpers and response-parsing
    logic defined in this module.

    Args:
        config: Application configuration containing category definitions.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._system_prompt = _build_system_prompt(config.categories)
        self._valid_names = {cat.name for cat in config.categories}

    @abstractmethod
    def classify(self, email_data: Dict[str, Any]) -> Optional[str]:
        """
        Classify a single email and return the matching category name.

        Args:
            email_data: Dict as returned by
                :meth:`~src.gmail_client.GmailClient.get_message`,
                with keys ``subject``, ``from_``, ``to``, ``date``,
                ``snippet``, ``body``.

        Returns:
            The category ``name`` string (e.g., ``"work"``), or ``None`` if
            no category was matched.
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the AI provider (e.g. ``"copilot"``)."""

    # ------------------------------------------------------------------
    # Shared helpers available to all subclasses
    # ------------------------------------------------------------------

    def _parse_category(self, raw: str) -> Optional[str]:
        """
        Extract a valid category name from a raw AI response string.

        Handles minor formatting variations (punctuation, extra whitespace,
        mixed case) and common refusal words (``none``, ``n/a``, etc.).

        Args:
            raw: AI response text, already stripped and lowercased.

        Returns:
            Matching category name string, or ``None``.
        """
        if raw in self._valid_names:
            return raw

        if raw in {"none", "n/a", "unknown", "other", "no match"}:
            return None

        # Strip punctuation and retry exact match.
        cleaned = re.sub(r"[^\w]", "", raw)
        if cleaned in self._valid_names:
            return cleaned

        # Substring search — handles responses like "category: work".
        for name in self._valid_names:
            if name in raw:
                return name

        logger.warning("Unrecognized classification response from %s: %r",
                       self.provider_name, raw)
        return None

    def _log_result(self, category: Optional[str], subject: str) -> None:
        """Log the classification outcome at the appropriate level."""
        if category:
            logger.info(
                "[%s] Classification result: '%s' (subject: %r)",
                self.provider_name,
                category,
                subject,
            )
        else:
            logger.info(
                "[%s] No category matched (subject: %r).",
                self.provider_name,
                subject,
            )


# ---------------------------------------------------------------------------
# GitHub Copilot backend
# ---------------------------------------------------------------------------

class CopilotClassifier(BaseClassifier):
    """
    Email classifier backed by GitHub Copilot's chat-completion API.

    GitHub Copilot exposes an OpenAI-compatible chat-completions endpoint at
    ``https://api.githubcopilot.com``.  Authentication uses a GitHub personal
    access token (classic) or fine-grained token with Copilot access, passed
    via the ``GITHUB_TOKEN`` environment variable.

    The ``openai`` Python package is used as the HTTP client; no separate
    Copilot SDK is required.

    Args:
        github_token: GitHub personal access token with Copilot access.
        config: Application configuration.
        model: Chat-completion model name supported by Copilot.
            Defaults to ``gpt-4o``.
    """

    _BASE_URL = "https://api.githubcopilot.com"

    def __init__(
        self,
        github_token: str,
        config: Config,
        model: str = _DEFAULT_COPILOT_MODEL,
    ) -> None:
        super().__init__(config)
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required to use the Copilot provider.\n"
                "Install it with: pip install openai"
            ) from exc

        self._client = OpenAI(
            api_key=github_token,
            base_url=self._BASE_URL,
        )
        self._model = model
        logger.info(
            "GitHub Copilot classifier initialised (model: %s, endpoint: %s).",
            model,
            self._BASE_URL,
        )

    @property
    def provider_name(self) -> str:
        return "copilot"

    def classify(self, email_data: Dict[str, Any]) -> Optional[str]:
        """
        Classify *email_data* using the GitHub Copilot chat-completion API.

        Raises:
            openai.OpenAIError: On unrecoverable API failures.
        """
        user_message = _format_email_for_prompt(email_data)
        subject = email_data.get("subject", "")

        logger.debug(
            "[copilot] Classifying email — subject: %r, from: %r",
            subject,
            email_data.get("from_"),
        )

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            temperature=0,  # Deterministic output for classification
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        raw_answer = (response.choices[0].message.content or "").strip().lower()

        category = self._parse_category(raw_answer)
        self._log_result(category, subject)
        return category


# ---------------------------------------------------------------------------
# OpenAI backend
# ---------------------------------------------------------------------------

class OpenAIClassifier(BaseClassifier):
    """
    Email classifier backed by an OpenAI-compatible chat-completion API.

    Works with any service that implements the OpenAI chat-completions
    interface, including the official OpenAI API, Azure OpenAI, and many
    self-hosted or third-party providers.

    Set ``OPENAI_BASE_URL`` in the environment to point at a non-OpenAI
    compatible endpoint (e.g., ``https://openrouter.ai/api/v1``).

    Args:
        api_key: OpenAI API key (``OPENAI_API_KEY``).
        config: Application configuration.
        model: Chat-completion model name.  Defaults to ``gpt-4o``.
        base_url: Optional API base URL override.  When ``None`` the SDK
            uses its built-in default (``https://api.openai.com/v1``).
    """

    def __init__(
        self,
        api_key: str,
        config: Config,
        model: str = _DEFAULT_OPENAI_MODEL,
        base_url: Optional[str] = None,
    ) -> None:
        super().__init__(config)
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required to use the OpenAI provider.\n"
                "Install it with: pip install openai"
            ) from exc

        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
            logger.info("OpenAI classifier using custom base URL: %s", base_url)

        self._client = OpenAI(**kwargs)
        self._model = model
        logger.info("OpenAI classifier initialised (model: %s).", model)

    @property
    def provider_name(self) -> str:
        return "openai"

    def classify(self, email_data: Dict[str, Any]) -> Optional[str]:
        """
        Classify *email_data* using an OpenAI chat-completion model.

        Raises:
            openai.OpenAIError: On unrecoverable OpenAI API failures.
        """
        user_message = _format_email_for_prompt(email_data)
        subject = email_data.get("subject", "")

        logger.debug(
            "[openai] Classifying email — subject: %r, from: %r",
            subject,
            email_data.get("from_"),
        )

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            temperature=0,  # Deterministic output for classification
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        raw_answer = (response.choices[0].message.content or "").strip().lower()

        category = self._parse_category(raw_answer)
        self._log_result(category, subject)
        return category


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_classifier(
    config: Config,
    github_token: str = "",
    openai_api_key: str = "",
    openai_base_url: Optional[str] = None,
) -> BaseClassifier:
    """
    Construct and return the classifier backend specified in *config*.

    The active provider is determined by ``config.ai_provider``:

    - ``"copilot"`` → :class:`CopilotClassifier`
    - ``"openai"``  → :class:`OpenAIClassifier`

    Args:
        config: Application configuration (contains ``ai_provider`` and
            the relevant model field).
        github_token: GitHub personal access token; required when provider
            is ``"copilot"``.
        openai_api_key: OpenAI API key; required when provider is
            ``"openai"``.
        openai_base_url: Optional base URL for OpenAI-compatible endpoints.

    Returns:
        A :class:`BaseClassifier` instance ready to call :meth:`~BaseClassifier.classify`.

    Raises:
        ValueError: If the provider is unknown or the required API key is
            missing.
    """
    provider = config.ai_provider.lower()

    if provider == "copilot":
        if not github_token:
            raise ValueError(
                "GITHUB_TOKEN is required when ai_provider is 'copilot'."
            )
        return CopilotClassifier(
            github_token=github_token,
            config=config,
            model=config.copilot_model,
        )

    if provider == "openai":
        if not openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when ai_provider is 'openai'."
            )
        return OpenAIClassifier(
            api_key=openai_api_key,
            config=config,
            model=config.openai_model,
            base_url=openai_base_url or None,
        )

    raise ValueError(
        f"Unknown ai_provider {provider!r}. "
        "Valid values are 'copilot' and 'openai'."
    )


# ---------------------------------------------------------------------------
# Shared prompt helpers
# ---------------------------------------------------------------------------

def _build_system_prompt(categories: List[Category]) -> str:
    """
    Build the classification system prompt from the category list.

    The same prompt text is used for both providers.  It is intentionally
    concise to minimise token costs while being unambiguous about the
    expected output format.

    Args:
        categories: Ordered list of :class:`~src.config_loader.Category` objects.

    Returns:
        System prompt string.
    """
    category_lines = []
    for cat in categories:
        line = f"- **{cat.name}**: {cat.description}"
        if cat.keywords:
            line += f" (hint keywords: {', '.join(cat.keywords)})"
        category_lines.append(line)

    categories_block = "\n".join(category_lines)

    return f"""You are an expert email classifier.

Given the metadata of an incoming email, classify it into exactly one of the
following categories. If none of the categories fit, respond with NONE.

## Categories

{categories_block}

## Instructions

1. Respond with ONLY the category name in lowercase (e.g., `work`) or the
   word `NONE` if no category applies.
2. Do not include any explanation, punctuation, or additional text.
3. Consider the sender domain, subject line, and email snippet carefully.
4. When in doubt between two categories, prefer the more specific one.
5. Automated notifications (CI/CD, monitoring alerts) should match the most
   relevant category based on context."""


def _format_email_for_prompt(email_data: Dict[str, Any]) -> str:
    """
    Format an email dict into a compact string for the AI prompt.

    Args:
        email_data: Dict with email fields as returned by
            :meth:`~src.gmail_client.GmailClient.get_message`.

    Returns:
        Formatted string containing the email metadata.
    """
    body_preview = (email_data.get("body") or email_data.get("snippet", ""))[:1_500]

    return (
        f"From: {email_data.get('from_', '')}\n"
        f"To: {email_data.get('to', '')}\n"
        f"Date: {email_data.get('date', '')}\n"
        f"Subject: {email_data.get('subject', '')}\n"
        f"\n"
        f"{body_preview}"
    ).strip()
