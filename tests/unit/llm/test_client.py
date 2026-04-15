"""Unit tests for GitHub Copilot LLM client behavior."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from gmail_sorter.config.models import LlmConfig
from gmail_sorter.llm.client import COPILOT_CHAT_COMPLETIONS_URL, LlmClient, LlmError


def _llm_config(max_retries: int = 2) -> LlmConfig:
    return LlmConfig(
        provider="github_copilot",
        model="gpt-4o",
        api_key_env="GITHUB_COPILOT_API_KEY",
        timeout_seconds=5,
        max_retries=max_retries,
        system_prompt="System",
        prompt_template="template",
    )


@pytest.mark.asyncio
@respx.mock
async def test_classify_sends_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client should call Copilot endpoint with expected headers and payload."""

    monkeypatch.setenv("GITHUB_COPILOT_API_KEY", "test-key")

    route = respx.post(COPILOT_CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "category": "alerts",
                                    "confidence": 0.88,
                                    "reasoning": "Automated event.",
                                }
                            )
                        }
                    }
                ]
            },
        )
    )

    client = LlmClient(_llm_config(), log_prompts=False)
    try:
        response = await client.classify("sys prompt", "user prompt")
    finally:
        await client.close()

    assert response.category == "alerts"
    assert response.confidence == 0.88
    assert route.called

    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.headers["Content-Type"] == "application/json"

    payload = json.loads(request.content.decode("utf-8"))
    assert payload["model"] == "gpt-4o"
    assert payload["messages"][0] == {"role": "system", "content": "sys prompt"}
    assert payload["messages"][1] == {"role": "user", "content": "user prompt"}


@pytest.mark.asyncio
@respx.mock
async def test_classify_retries_and_raises_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client should retry failing calls and raise LlmError after exhaustion."""

    monkeypatch.setenv("GITHUB_COPILOT_API_KEY", "test-key")

    route = respx.post(COPILOT_CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(500, json={"error": "server error"})
    )

    client = LlmClient(_llm_config(max_retries=2), log_prompts=False)
    try:
        with pytest.raises(LlmError):
            await client.classify("sys", "user")
    finally:
        await client.close()

    assert route.call_count == 3


def test_init_raises_system_exit_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client initialization should fail fast when API key env var is absent."""

    monkeypatch.delenv("GITHUB_COPILOT_API_KEY", raising=False)

    with pytest.raises(SystemExit):
        LlmClient(_llm_config(), log_prompts=False)


@pytest.mark.asyncio
@respx.mock
async def test_classify_logs_lengths_when_prompts_redacted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When prompt logging is disabled, logs should contain lengths not prompt text."""

    monkeypatch.setenv("GITHUB_COPILOT_API_KEY", "test-key")

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
                                    "confidence": 0.5,
                                    "reasoning": "Reason.",
                                }
                            )
                        }
                    }
                ]
            },
        )
    )

    caplog.set_level("DEBUG")
    client = LlmClient(_llm_config(), log_prompts=False)
    try:
        await client.classify("sensitive system", "sensitive user")
    finally:
        await client.close()

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "LLM request lengths:" in logs
    assert "sensitive system" not in logs
    assert "sensitive user" not in logs
