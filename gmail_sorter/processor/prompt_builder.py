"""Prompt construction utilities for LLM classification."""

from __future__ import annotations

import hashlib
from pathlib import Path

from jinja2 import Template

from gmail_sorter.config.models import CategoryConfig, LlmConfig
from gmail_sorter.processor.email_parser import ProcessedEmail


class PromptBuilder:
    """Render user prompts for LLM classification requests."""

    def __init__(self, config: LlmConfig, categories: list[CategoryConfig]) -> None:
        """Initialize prompt rendering with template source and category list."""

        self._config = config
        self._categories = categories
        self._template_source = self._load_template_source(config.prompt_template)
        self._template = Template(self._template_source)

    def build(self, email: ProcessedEmail) -> tuple[str, str]:
        """Render and return ``(system_prompt, user_prompt)`` for a message."""

        user_prompt = self._template.render(
            sender=email.sender,
            subject=email.subject,
            body=email.body,
            date=email.date,
            headers=email.headers,
            categories=self._categories,
        )
        return self._config.system_prompt, user_prompt

    def template_hash(self) -> str:
        """Return a stable SHA-256 hash of the template source text."""

        return hashlib.sha256(self._template_source.encode("utf-8")).hexdigest()

    @staticmethod
    def _load_template_source(template_value: str) -> str:
        """Load template source from a file path or inline template string."""

        template_path = Path(template_value)
        if template_path.exists() and template_path.is_file():
            return template_path.read_text(encoding="utf-8")
        return template_value
