"""
AI-powered email classifier using Claude.

Sends email metadata to Claude (``claude-opus-4-6`` with adaptive thinking) and
returns the matching category name defined in the user's configuration.

The system prompt — which includes all category definitions — is sent with
``cache_control: {"type": "ephemeral"}`` so that repeated classification calls
within a 5-minute window benefit from Anthropic's prompt caching (up to ~90%
cost reduction on the cached prefix).
"""

import logging
import re
from typing import Any, Dict, List, Optional

import anthropic

from src.config_loader import Category, Config

logger = logging.getLogger(__name__)

# The model used for all classification requests.
_MODEL = "claude-opus-4-6"

# Maximum tokens allocated for the classification response.
# The answer is a single category name, so this is intentionally small.
_MAX_TOKENS = 256


class Classifier:
    """
    Classifies emails into user-defined categories using Claude AI.

    Builds a cached system prompt from the configuration categories and
    sends each email's metadata as a user message.  Claude is instructed
    to respond with only the category name (or ``NONE`` if no category fits).

    Args:
        api_key: Anthropic API key.
        config: Application configuration containing the category definitions.
    """

    def __init__(self, api_key: str, config: Config) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._config = config
        self._system_prompt = _build_system_prompt(config.categories)
        self._valid_names = {cat.name for cat in config.categories}

    def classify(self, email_data: Dict[str, Any]) -> Optional[str]:
        """
        Classify a single email and return the matching category name.

        Args:
            email_data: Dict as returned by :meth:`~src.gmail_client.GmailClient.get_message`,
                with keys ``subject``, ``from_``, ``to``, ``date``, ``snippet``, ``body``.

        Returns:
            The category ``name`` string (e.g., ``"work"``), or ``None`` if
            Claude returns ``NONE`` or an unrecognized value.

        Raises:
            anthropic.APIError: On unrecoverable Anthropic API failures.
        """
        user_message = _format_email_for_prompt(email_data)

        logger.debug(
            "Classifying email — subject: %r, from: %r",
            email_data.get("subject"),
            email_data.get("from_"),
        )

        with self._client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": self._system_prompt,
                    # Cache the system prompt; it is identical for every
                    # classification call within this session.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            response = stream.get_final_message()

        # Extract the text response from content blocks.
        raw_answer = ""
        for block in response.content:
            if block.type == "text":
                raw_answer = block.text.strip().lower()
                break

        category = self._parse_category(raw_answer)

        if category:
            logger.info(
                "Classification result: '%s' (subject: %r)",
                category,
                email_data.get("subject"),
            )
        else:
            logger.info(
                "No category matched for email (subject: %r). "
                "Raw response: %r",
                email_data.get("subject"),
                raw_answer,
            )

        return category

    def _parse_category(self, raw: str) -> Optional[str]:
        """
        Extract a valid category name from Claude's raw response.

        Handles minor formatting variations (e.g., surrounding punctuation
        or extra whitespace) by stripping and lowercasing.

        Args:
            raw: Claude's raw text response, already stripped and lowercased.

        Returns:
            Matching category name, or None.
        """
        # Exact match first.
        if raw in self._valid_names:
            return raw

        # Handle "NONE" (case-insensitive).
        if raw in {"none", "n/a", "unknown", "other"}:
            return None

        # Strip punctuation and try again.
        cleaned = re.sub(r"[^\w]", "", raw)
        if cleaned in self._valid_names:
            return cleaned

        # Search for any valid category name appearing anywhere in the response.
        for name in self._valid_names:
            if name in raw:
                return name

        logger.warning("Unrecognized classification response: %r", raw)
        return None


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _build_system_prompt(categories: List[Category]) -> str:
    """
    Build the classification system prompt from the category list.

    The prompt is intentionally concise to minimize token costs while
    being unambiguous about the expected output format.

    Args:
        categories: Ordered list of :class:`~src.config_loader.Category` objects.

    Returns:
        The system prompt string to use for all classification requests.
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
    Format an email dict into a compact prompt string for Claude.

    Args:
        email_data: Dict with email fields as returned by
            :meth:`~src.gmail_client.GmailClient.get_message`.

    Returns:
        A formatted string containing the email metadata.
    """
    # Truncate the body to avoid excessive token usage.
    body_preview = (email_data.get("body") or email_data.get("snippet", ""))[:1_500]

    return (
        f"From: {email_data.get('from_', '')}\n"
        f"To: {email_data.get('to', '')}\n"
        f"Date: {email_data.get('date', '')}\n"
        f"Subject: {email_data.get('subject', '')}\n"
        f"\n"
        f"{body_preview}"
    ).strip()
