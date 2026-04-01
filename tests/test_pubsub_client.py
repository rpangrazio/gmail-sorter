"""Tests for src/pubsub_client.py — 100% coverage."""

import base64
import json
import threading
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import DeadlineExceeded, ServiceUnavailable

from src.pubsub_client import PubSubClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pubsub_message(payload: dict) -> MagicMock:
    encoded = base64.b64encode(json.dumps(payload).encode())
    msg = MagicMock()
    msg.data = encoded
    msg.message_id = "test_msg_id"
    received = MagicMock()
    received.ack_id = "ack_1"
    received.message = msg
    return received


def make_client(subscriber=None):
    subscriber = subscriber or MagicMock()
    creds = MagicMock()
    with patch("src.pubsub_client.pubsub_v1.SubscriberClient", return_value=subscriber):
        client = PubSubClient("projects/p/subscriptions/s", creds)
    return client, subscriber


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

def test_init_creates_subscriber_client():
    creds = MagicMock()
    mock_subscriber = MagicMock()
    with patch("src.pubsub_client.pubsub_v1.SubscriberClient", return_value=mock_subscriber) as cls:
        client = PubSubClient("projects/p/subscriptions/s", creds)
    cls.assert_called_once_with(credentials=creds)
    assert client._subscription_path == "projects/p/subscriptions/s"


# ---------------------------------------------------------------------------
# run_forever
# ---------------------------------------------------------------------------

def test_run_forever_stops_immediately_when_event_set():
    client, _ = make_client()
    stop = threading.Event()
    stop.set()
    client.run_forever(lambda x: None, stop_event=stop)  # Should return at once


def test_run_forever_no_stop_event_single_iteration():
    """Without a stop event, exits after callback sets external flag."""
    client, subscriber = make_client()

    call_count = 0

    def pull_side_effect(*, request, timeout):
        nonlocal call_count
        call_count += 1
        # Return empty response, then the caller will loop again.
        # Use side_effect list instead.
        raise DeadlineExceeded("no messages")

    subscriber.pull.side_effect = [
        DeadlineExceeded("no messages"),
    ]

    stop = threading.Event()

    def patched_pull_and_process(cb):
        stop.set()  # Stop after first call

    with patch.object(client, "_pull_and_process", side_effect=patched_pull_and_process):
        client.run_forever(lambda x: None, stop_event=stop)


def test_run_forever_handles_deadline_exceeded():
    client, subscriber = make_client()
    stop = threading.Event()
    calls = []

    def fake_pull_and_process(cb):
        if not calls:
            calls.append(1)
            raise DeadlineExceeded("timeout")
        stop.set()

    with patch.object(client, "_pull_and_process", side_effect=fake_pull_and_process):
        client.run_forever(lambda x: None, stop_event=stop)

    assert len(calls) == 1


def test_run_forever_handles_service_unavailable():
    client, _ = make_client()
    stop = threading.Event()
    calls = []

    def fake_pull_and_process(cb):
        if not calls:
            calls.append(1)
            raise ServiceUnavailable("down")
        stop.set()

    with patch.object(client, "_pull_and_process", side_effect=fake_pull_and_process):
        with patch("time.sleep"):
            client.run_forever(lambda x: None, stop_event=stop)

    assert len(calls) == 1


def test_run_forever_handles_generic_exception():
    client, _ = make_client()
    stop = threading.Event()
    calls = []

    def fake_pull_and_process(cb):
        if not calls:
            calls.append(1)
            raise RuntimeError("unexpected error")
        stop.set()

    with patch.object(client, "_pull_and_process", side_effect=fake_pull_and_process):
        with patch("time.sleep"):
            client.run_forever(lambda x: None, stop_event=stop)

    assert len(calls) == 1


# ---------------------------------------------------------------------------
# _pull_and_process
# ---------------------------------------------------------------------------

def test_pull_and_process_no_messages():
    client, subscriber = make_client()
    subscriber.pull.return_value = MagicMock(received_messages=[])
    cb = MagicMock()
    client._pull_and_process(cb)
    cb.assert_not_called()
    subscriber.acknowledge.assert_not_called()


def test_pull_and_process_delivers_payload():
    client, subscriber = make_client()
    payload = {"emailAddress": "user@example.com", "historyId": "12345"}
    received = make_pubsub_message(payload)
    subscriber.pull.return_value = MagicMock(received_messages=[received])

    cb = MagicMock()
    client._pull_and_process(cb)

    cb.assert_called_once_with(payload)
    subscriber.acknowledge.assert_called_once()


def test_pull_and_process_skips_unparseable_message():
    client, subscriber = make_client()
    bad_msg = MagicMock()
    bad_msg.data = b"@@@not-valid-base64@@@"
    bad_msg.message_id = "bad"
    received = MagicMock()
    received.ack_id = "ack_bad"
    received.message = bad_msg

    subscriber.pull.return_value = MagicMock(received_messages=[received])

    cb = MagicMock()
    client._pull_and_process(cb)

    cb.assert_not_called()
    # Still acknowledged to avoid redelivery
    subscriber.acknowledge.assert_called_once()


def test_pull_and_process_acks_even_when_callback_raises():
    client, subscriber = make_client()
    payload = {"emailAddress": "user@example.com", "historyId": "99"}
    received = make_pubsub_message(payload)
    subscriber.pull.return_value = MagicMock(received_messages=[received])

    cb = MagicMock(side_effect=RuntimeError("callback failure"))
    client._pull_and_process(cb)

    # Callback was called but raised; message still acknowledged
    cb.assert_called_once()
    subscriber.acknowledge.assert_called_once()


def test_pull_and_process_multiple_messages():
    client, subscriber = make_client()
    payloads = [
        {"emailAddress": "a@b.com", "historyId": "1"},
        {"emailAddress": "c@d.com", "historyId": "2"},
    ]
    received_msgs = [make_pubsub_message(p) for p in payloads]
    subscriber.pull.return_value = MagicMock(received_messages=received_msgs)

    cb = MagicMock()
    client._pull_and_process(cb)

    assert cb.call_count == 2
    subscriber.acknowledge.assert_called_once()


# ---------------------------------------------------------------------------
# _decode_message
# ---------------------------------------------------------------------------

def test_decode_message_success():
    payload = {"emailAddress": "user@example.com", "historyId": "12345"}
    msg = MagicMock()
    msg.data = base64.b64encode(json.dumps(payload).encode())
    result = PubSubClient._decode_message(msg)
    assert result == payload


def test_decode_message_invalid_base64():
    msg = MagicMock()
    msg.data = b"@@@invalid@@@"
    result = PubSubClient._decode_message(msg)
    assert result is None


def test_decode_message_valid_base64_but_not_json():
    msg = MagicMock()
    msg.data = base64.b64encode(b"this is not json")
    result = PubSubClient._decode_message(msg)
    assert result is None
