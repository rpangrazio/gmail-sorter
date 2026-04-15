"""Integration tests for LLM HTTP client behavior."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from gmail_sorter.config.models import LlmConfig
from gmail_sorter.llm.client import COPILOT_CHAT_COMPLETIONS_URL, LlmClient, LlmError


def _config(max_retries: int = 2) -> LlmConfig:
    return LlmConfig(
        provider="github_copilot",
        model="gpt-4o",
        api_key_env="GITHUB_COPILOT_API_KEY",
        timeout_seconds=5,
        max_retries=max_retries,
        system_prompt="System prompt",
        prompt_template="template",
    )


@pytest.mark.asyncio
@respx.mock
async def test_classify_parses_structured_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client should return parsed category/confidence on a successful call."""

    monkeypatch.setenv("GITHUB_COPILOT_API_KEY", "integration-key")

    respx.post(COPILOT_CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "category": "alerts",
                                    "confidence": 0.82,
                                    "reasoning": "Automated system event.",
                                }
                            )
                        }
                    }
                ]
            },
        )
    )

    client = LlmClient(_config(max_retries=1), log_prompts=False)
    try:
        result = await client.classify("sys", "user")
    finally:
        await client.close()

    assert result.category == "alerts"
    assert result.confidence == 0.82


@pytest.mark.asyncio
@respx.mock
async def test_classify_raises_llm_error_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated 500 responses should raise LlmError after configured retries."""

    monkeypatch.setenv("GITHUB_COPILOT_API_KEY", "integration-key")

    route = respx.post(COPILOT_CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(500, json={"error": "server error"})
    )

    client = LlmClient(_config(max_retries=2), log_prompts=False)
    try:
        with pytest.raises(LlmError):
            await client.classify("sys", "user")
    finally:
        await client.close()

    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_classify_retries_on_timeout_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout exceptions should trigger retry and allow later success."""

    monkeypatch.setenv("GITHUB_COPILOT_API_KEY", "integration-key")

    request = httpx.Request("POST", COPILOT_CHAT_COMPLETIONS_URL)
    respx.post(COPILOT_CHAT_COMPLETIONS_URL).mock(
        side_effect=[
            httpx.TimeoutException("Timed out", request=request),
            httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "category": "alerts",
                                        "confidence": 0.7,
                                        "reasoning": "Recovered after retry.",
                                    }
                                )
                            }
                        }
                    ]
                },
            ),
        ]
    )

    client = LlmClient(_config(max_retries=2), log_prompts=False)
    try:
        result = await client.classify("sys", "user")
    finally:
        await client.close()

    assert result.category == "alerts"
    assert result.confidence == 0.7
