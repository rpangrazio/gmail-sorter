"""Unit tests for prompt builder behavior."""

from __future__ import annotations

import hashlib

from gmail_sorter.config.models import CategoryConfig, LlmConfig
from gmail_sorter.processor.email_parser import ProcessedEmail
from gmail_sorter.processor.prompt_builder import PromptBuilder


def _llm_config(template: str) -> LlmConfig:
    return LlmConfig(
            provider="openai_compatible",
        model="gpt-4o",
            api_key_env="OPENAI_API_KEY",
        timeout_seconds=30,
        max_retries=3,
        system_prompt="System directive",
        prompt_template=template,
    )


def _categories() -> list[CategoryConfig]:
    return [
        CategoryConfig(name="marketing", label="AutoSort/Marketing", description="Promos"),
        CategoryConfig(name="alerts", label="AutoSort/Alerts", description="Notifications"),
    ]


def _email() -> ProcessedEmail:
    return ProcessedEmail(
        message_id="msg-1",
        thread_id="thread-1",
        sender="sender@example.com",
        subject="Subject A",
        date="2026-04-15",
        body="Email body",
        headers={"list_unsubscribe": "false", "reply_to": "reply@example.com"},
        raw_label_ids=["INBOX"],
    )


def test_build_renders_sender_subject_and_categories() -> None:
    """Rendered prompt should include contextual email fields and category list."""

    template = (
        "Sender={{ sender }} Subject={{ subject }} Categories="
        "{% for cat in categories %}{{ cat.name }} {% endfor %}"
    )
    builder = PromptBuilder(_llm_config(template), _categories())

    system_prompt, user_prompt = builder.build(_email())

    assert system_prompt == "System directive"
    assert "Sender=sender@example.com" in user_prompt
    assert "Subject=Subject A" in user_prompt
    assert "marketing" in user_prompt
    assert "alerts" in user_prompt


def test_inline_template_is_supported() -> None:
    """Inline template strings should render without requiring a file."""

    template = "{{ sender }}|{{ subject }}|{{ body }}"
    builder = PromptBuilder(_llm_config(template), _categories())

    _, user_prompt = builder.build(_email())
    assert user_prompt == "sender@example.com|Subject A|Email body"


def test_file_template_is_supported(tmp_path) -> None:
    """Template source should load from a file path when it exists."""

    template_path = tmp_path / "prompt.j2"
    template_path.write_text("From file: {{ sender }}", encoding="utf-8")

    builder = PromptBuilder(_llm_config(str(template_path)), _categories())
    _, user_prompt = builder.build(_email())

    assert user_prompt == "From file: sender@example.com"


def test_template_hash_is_stable() -> None:
    """Template hash should be deterministic for identical template source."""

    template = "{{ sender }}"
    builder = PromptBuilder(_llm_config(template), _categories())

    expected = hashlib.sha256(template.encode("utf-8")).hexdigest()
    assert builder.template_hash() == expected
