"""Tests for src/gmail_client.py — 100% coverage."""

import base64
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from src.gmail_client import (
    GmailClient,
    HistoryExpiredError,
    _decode_base64url,
    _extract_body,
    _strip_html_tags,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"Error")


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


@pytest.fixture
def service():
    return MagicMock()


@pytest.fixture
def client(service):
    return GmailClient(service)


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------

def test_get_profile(client, service):
    service.users().getProfile().execute.return_value = {
        "emailAddress": "user@example.com",
        "historyId": "12345",
    }
    result = client.get_profile()
    assert result["emailAddress"] == "user@example.com"


# ---------------------------------------------------------------------------
# ensure_watch
# ---------------------------------------------------------------------------

def test_ensure_watch_skips_when_not_expiring(client, service):
    state = MagicMock()
    state.is_watch_expiring_soon.return_value = False
    client.ensure_watch("projects/p/topics/t", state)
    service.users().watch.assert_not_called()


def test_ensure_watch_registers(client, service):
    state = MagicMock()
    state.is_watch_expiring_soon.return_value = True
    service.users().watch().execute.return_value = {
        "historyId": "99999",
        "expiration": "1234567890000",
    }
    client.ensure_watch("projects/p/topics/t", state)
    state.set_watch_expiry.assert_called_once_with(1234567890000)


# ---------------------------------------------------------------------------
# list_new_messages
# ---------------------------------------------------------------------------

def test_list_new_messages_empty_history(client, service):
    service.users().history().list().execute.return_value = {"history": []}
    ids, max_id = client.list_new_messages("100")
    assert ids == []
    assert max_id == "100"


def test_list_new_messages_no_history_key(client, service):
    """Response with no 'history' key at all."""
    service.users().history().list().execute.return_value = {}
    ids, max_id = client.list_new_messages("100")
    assert ids == []
    assert max_id == "100"


def test_list_new_messages_inbox_message(client, service):
    service.users().history().list().execute.return_value = {
        "history": [
            {
                "id": "200",
                "messagesAdded": [
                    {"message": {"id": "msg1", "labelIds": ["INBOX"]}}
                ],
            }
        ]
    }
    ids, max_id = client.list_new_messages("100")
    assert "msg1" in ids
    assert max_id == "200"


def test_list_new_messages_record_without_id(client, service):
    """Record has no 'id' → falls back to start_history_id, max_id unchanged."""
    service.users().history().list().execute.return_value = {
        "history": [
            {
                # No "id" key
                "messagesAdded": [
                    {"message": {"id": "msg1", "labelIds": ["INBOX"]}}
                ],
            }
        ]
    }
    ids, max_id = client.list_new_messages("100")
    assert "msg1" in ids
    assert max_id == "100"  # Not advanced since record_history_id == start_history_id


def test_list_new_messages_skips_sent(client, service):
    service.users().history().list().execute.return_value = {
        "history": [
            {
                "id": "200",
                "messagesAdded": [
                    {"message": {"id": "sent_msg", "labelIds": ["INBOX", "SENT"]}},
                ],
            }
        ]
    }
    ids, _ = client.list_new_messages("100")
    assert "sent_msg" not in ids


def test_list_new_messages_skips_draft(client, service):
    service.users().history().list().execute.return_value = {
        "history": [
            {
                "id": "200",
                "messagesAdded": [
                    {"message": {"id": "draft_msg", "labelIds": ["DRAFT"]}},
                ],
            }
        ]
    }
    ids, _ = client.list_new_messages("100")
    assert ids == []


def test_list_new_messages_skips_spam(client, service):
    service.users().history().list().execute.return_value = {
        "history": [
            {
                "id": "200",
                "messagesAdded": [
                    {"message": {"id": "spam_msg", "labelIds": ["INBOX", "SPAM"]}},
                ],
            }
        ]
    }
    ids, _ = client.list_new_messages("100")
    assert "spam_msg" not in ids


def test_list_new_messages_skips_no_inbox(client, service):
    service.users().history().list().execute.return_value = {
        "history": [
            {
                "id": "200",
                "messagesAdded": [
                    {"message": {"id": "noinbox", "labelIds": ["CATEGORY_UPDATES"]}},
                ],
            }
        ]
    }
    ids, _ = client.list_new_messages("100")
    assert ids == []


def test_list_new_messages_pagination(client, service):
    service.users().history().list().execute.side_effect = [
        {
            "history": [
                {
                    "id": "200",
                    "messagesAdded": [
                        {"message": {"id": "msg1", "labelIds": ["INBOX"]}}
                    ],
                }
            ],
            "nextPageToken": "token123",
        },
        {
            "history": [
                {
                    "id": "300",
                    "messagesAdded": [
                        {"message": {"id": "msg2", "labelIds": ["INBOX"]}}
                    ],
                }
            ],
        },
    ]
    ids, max_id = client.list_new_messages("100")
    assert "msg1" in ids
    assert "msg2" in ids
    assert max_id == "300"


def test_list_new_messages_404_raises_history_expired(client, service):
    service.users().history().list().execute.side_effect = make_http_error(404)
    with pytest.raises(HistoryExpiredError):
        client.list_new_messages("too_old")


def test_list_new_messages_non_404_http_error_reraises(client, service):
    service.users().history().list().execute.side_effect = make_http_error(403)
    with pytest.raises(HttpError):
        client.list_new_messages("100")


# ---------------------------------------------------------------------------
# get_message
# ---------------------------------------------------------------------------

def test_get_message_plain_text(client, service):
    service.users().messages().get().execute.return_value = {
        "id": "msg123",
        "snippet": "Hello world",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "Test Subject"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Date", "value": "Mon, 1 Jan 2024"},
            ],
            "body": {"data": b64("Hello, plain text!")},
        },
    }
    result = client.get_message("msg123")
    assert result["id"] == "msg123"
    assert result["subject"] == "Test Subject"
    assert result["from_"] == "sender@example.com"
    assert result["to"] == "recipient@example.com"
    assert result["date"] == "Mon, 1 Jan 2024"
    assert result["snippet"] == "Hello world"
    assert "Hello, plain text!" in result["body"]


def test_get_message_missing_headers(client, service):
    """Missing headers fall back to defaults."""
    service.users().messages().get().execute.return_value = {
        "id": "msg_no_headers",
        "snippet": "",
        "payload": {
            "mimeType": "text/plain",
            "headers": [],
            "body": {},
        },
    }
    result = client.get_message("msg_no_headers")
    assert result["subject"] == "(no subject)"
    assert result["from_"] == "(unknown sender)"


# ---------------------------------------------------------------------------
# apply_label
# ---------------------------------------------------------------------------

def test_apply_label(client, service):
    service.users().messages().modify().execute.return_value = {}
    client.apply_label("msg123", "Label_456")
    service.users().messages().modify.assert_called()


# ---------------------------------------------------------------------------
# _execute — retry logic
# ---------------------------------------------------------------------------

def test_execute_success(client):
    req = MagicMock()
    req.execute.return_value = {"ok": True}
    assert client._execute(req) == {"ok": True}


def test_execute_retries_429(client):
    req = MagicMock()
    req.execute.side_effect = [make_http_error(429), {"ok": True}]
    with patch("time.sleep"):
        result = client._execute(req)
    assert result == {"ok": True}


def test_execute_retries_500(client):
    req = MagicMock()
    req.execute.side_effect = [make_http_error(500), {"ok": True}]
    with patch("time.sleep"):
        result = client._execute(req)
    assert result == {"ok": True}


def test_execute_raises_immediately_on_403(client):
    req = MagicMock()
    req.execute.side_effect = make_http_error(403)
    with pytest.raises(HttpError):
        client._execute(req)


def test_execute_exhausts_all_retries(client):
    """After MAX_RETRIES consecutive 429s, raises an exception."""
    req = MagicMock()
    req.execute.side_effect = make_http_error(429)
    with patch("time.sleep"):
        with pytest.raises(Exception):
            client._execute(req)


# ---------------------------------------------------------------------------
# _extract_body
# ---------------------------------------------------------------------------

def test_extract_body_text_plain_direct():
    payload = {"mimeType": "text/plain", "body": {"data": b64("Plain text body")}}
    assert _extract_body(payload) == "Plain text body"


def test_extract_body_prefers_plain_in_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "body": {},
        "parts": [
            {"mimeType": "text/html", "body": {"data": b64("<p>HTML</p>")}},
            {"mimeType": "text/plain", "body": {"data": b64("Plain preferred")}},
        ],
    }
    assert _extract_body(payload) == "Plain preferred"


def test_extract_body_plain_part_with_empty_data_then_recursive():
    """Plain part exists but has no data; recurse falls through."""
    payload = {
        "mimeType": "multipart/mixed",
        "body": {},
        "parts": [
            {"mimeType": "text/plain", "body": {"data": ""}},
        ],
    }
    # Empty data → skip; recursive call on same part also returns ""
    assert _extract_body(payload) == ""


def test_extract_body_html_fallback():
    payload = {
        "mimeType": "text/html",
        "body": {"data": b64("<p>HTML content here</p>")},
        "parts": [],
    }
    result = _extract_body(payload)
    assert "HTML content here" in result


def test_extract_body_empty_payload():
    payload = {"mimeType": "multipart/mixed", "body": {}, "parts": []}
    assert _extract_body(payload) == ""


def test_extract_body_recursive_nested():
    payload = {
        "mimeType": "multipart/mixed",
        "body": {},
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "body": {},
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": b64("Nested plain")}},
                ],
            }
        ],
    }
    assert _extract_body(payload) == "Nested plain"


def test_extract_body_max_chars():
    long_text = "x" * 20_000
    payload = {"mimeType": "text/plain", "body": {"data": b64(long_text)}}
    result = _extract_body(payload, max_chars=100)
    assert len(result) == 100


# ---------------------------------------------------------------------------
# _decode_base64url
# ---------------------------------------------------------------------------

def test_decode_base64url_roundtrip():
    original = "Hello, world! 🌍"
    encoded = base64.urlsafe_b64encode(original.encode()).decode()
    assert _decode_base64url(encoded) == original


def test_decode_base64url_with_padding_issue():
    # Encode without padding
    raw = b"test data"
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    assert _decode_base64url(encoded) == "test data"


def test_decode_base64url_exception_returns_empty():
    # Force the except branch by making the decoder raise
    with patch("src.gmail_client.base64.urlsafe_b64decode", side_effect=Exception("decode error")):
        result = _decode_base64url("any_input")
    assert result == ""


# ---------------------------------------------------------------------------
# _strip_html_tags
# ---------------------------------------------------------------------------

def test_strip_html_tags_removes_tags():
    result = _strip_html_tags("<p>Hello <b>World</b></p>")
    assert "Hello" in result
    assert "World" in result
    assert "<" not in result


def test_strip_html_tags_removes_script():
    result = _strip_html_tags("<script>alert('xss')</script>Safe text")
    assert "alert" not in result
    assert "Safe text" in result


def test_strip_html_tags_removes_style():
    result = _strip_html_tags("<style>body { color: red }</style>Visible")
    assert "color" not in result
    assert "Visible" in result


def test_strip_html_tags_block_elements_become_newlines():
    result = _strip_html_tags("<div>Line1</div><div>Line2</div>")
    assert "Line1" in result
    assert "Line2" in result
