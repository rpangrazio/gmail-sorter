"""Email processing and prompt-building components."""

from gmail_sorter.processor.email_parser import ProcessedEmail, process_message
from gmail_sorter.processor.prompt_builder import PromptBuilder

__all__ = ["ProcessedEmail", "PromptBuilder", "process_message"]
