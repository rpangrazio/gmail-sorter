"""GitHub Copilot LLM client implementation.

This module provides the async HTTP integration used for classification calls
and enforces API-key loading and retry behavior.
"""

from __future__ import annotations

import logging
import os
import ssl
from typing import Any

import httpx

from gmail_sorter.config.models import LlmConfig
from gmail_sorter.llm.response_parser import LlmResponse, parse_response
from gmail_sorter.utils.tls import ensure_tls12_context
from gmail_sorter.utils.retry import with_retry

LOGGER = logging.getLogger(__name__)

COPILOT_CHAT_COMPLETIONS_URL = "https://api.githubcopilot.com/chat/completions"


class LlmError(RuntimeError):
    """Raised when an LLM API call fails permanently."""


class LlmClient:
    """Async client for GitHub Copilot chat completions."""

    def __init__(
        self,
        config: LlmConfig,
        log_prompts: bool = False,
        tls_context: ssl.SSLContext | None = None,
    ) -> None:
        """Initialize HTTP client and resolve API key from environment."""

        self._config = config
        self._log_prompts = log_prompts

        try:
            self._api_key = os.environ[config.api_key_env]
        except KeyError as exc:
            raise SystemExit(
                f"Required environment variable {config.api_key_env!r} is not set."
            ) from exc

        self._tls_context = ensure_tls12_context(tls_context)

        self._http_client = httpx.AsyncClient(
            http2=True,
            timeout=config.timeout_seconds,
            verify=self._tls_context,
        )

    async def classify(self, system_prompt: str, user_prompt: str) -> LlmResponse:
        """Send prompts to Copilot and return parsed classification output."""

        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        if self._log_prompts:
            LOGGER.debug("LLM request prompts: %s", payload["messages"])
        else:
            LOGGER.debug(
                "LLM request lengths: system=%s user=%s",
                len(system_prompt),
                len(user_prompt),
            )

        response = await self._post_with_retry(payload=payload, headers=headers)
        raw_content = self._extract_response_content(response)

        if self._log_prompts:
            LOGGER.debug("LLM raw response: %s", raw_content)
        else:
            LOGGER.debug("LLM response length: %s", len(raw_content))

        return parse_response(
            raw_content=raw_content,
            valid_categories=[],
            fallback="uncategorized",
            threshold=0.0,
            multi_label=False,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._http_client.aclose()

    async def _post_with_retry(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        """Execute POST with retry and status handling."""

        @with_retry(
            max_retries=self._config.max_retries,
            retryable_exceptions=(httpx.HTTPError, httpx.TimeoutException),
        )
        async def _send() -> httpx.Response:
            response = await self._http_client.post(
                COPILOT_CHAT_COMPLETIONS_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response

        try:
            return await _send()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise LlmError("LLM API request failed after retries.") from exc
        except Exception as exc:  # pragma: no cover - defensive safeguard
            raise LlmError("Unexpected error while calling LLM API.") from exc

    @staticmethod
    def _extract_response_content(response: httpx.Response) -> str:
        """Extract content string from Copilot chat completions payload."""

        try:
            body = response.json()
        except ValueError as exc:
            raise LlmError("LLM API returned a non-JSON response.") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError("LLM API response did not contain message content.") from exc

        if not isinstance(content, str):
            raise LlmError("LLM API response content must be a string.")

        return content
