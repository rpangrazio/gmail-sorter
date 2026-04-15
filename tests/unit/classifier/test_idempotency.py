"""Unit tests for classification idempotency checks."""

from __future__ import annotations

from gmail_sorter.classifier.idempotency import IdempotencyChecker
from gmail_sorter.processor.email_parser import ProcessedEmail


class _FakeDatabase:
    def __init__(self, classified_message_ids: set[str]) -> None:
        self._classified_message_ids = classified_message_ids

    def is_classified(self, message_id: str) -> bool:
        return message_id in self._classified_message_ids


def _email(message_id: str, raw_label_ids: list[str]) -> ProcessedEmail:
    return ProcessedEmail(
        message_id=message_id,
        thread_id="thread-1",
        sender="sender@example.com",
        subject="subject",
        date="2026-04-15",
        body="body",
        headers={},
        raw_label_ids=raw_label_ids,
    )


def test_is_processed_when_already_in_database() -> None:
    checker = IdempotencyChecker(
        db=_FakeDatabase(classified_message_ids={"msg-1"}),
        system_label_ids={"Label_123"},
    )

    assert checker.is_processed(_email("msg-1", raw_label_ids=[])) is True


def test_is_processed_when_system_label_present() -> None:
    checker = IdempotencyChecker(
        db=_FakeDatabase(classified_message_ids=set()),
        system_label_ids={"Label_123"},
    )

    assert checker.is_processed(_email("msg-2", raw_label_ids=["INBOX", "Label_123"])) is True


def test_is_not_processed_when_missing_db_record_and_system_label() -> None:
    checker = IdempotencyChecker(
        db=_FakeDatabase(classified_message_ids=set()),
        system_label_ids={"Label_123"},
    )

    assert checker.is_processed(_email("msg-3", raw_label_ids=["INBOX"])) is False
