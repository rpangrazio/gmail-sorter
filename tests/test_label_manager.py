"""Tests for src/label_manager.py — 100% coverage."""

from unittest.mock import MagicMock, call

import pytest
from googleapiclient.errors import HttpError

from src.label_manager import LabelManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"Error")


def make_service(labels=None):
    """Return a Gmail service mock pre-loaded with an initial label list."""
    service = MagicMock()
    labels = labels or []
    service.users().labels().list().execute.return_value = {"labels": labels}
    return service


# ---------------------------------------------------------------------------
# get_or_create_label
# ---------------------------------------------------------------------------

def test_get_or_create_label_cache_hit():
    service = make_service()
    lm = LabelManager(service)
    lm._cache = {"AI-Sorted/Work": "Label_123"}
    lm._cache_populated = True

    result = lm.get_or_create_label("AI-Sorted/Work")

    assert result == "Label_123"
    service.users().labels().create.assert_not_called()


def test_get_or_create_label_from_existing(make_gmail_service_with_labels):
    """Label is already on Gmail; no creation needed."""
    service = make_service(labels=[{"name": "MyLabel", "id": "Label_existing"}])
    lm = LabelManager(service)

    result = lm.get_or_create_label("MyLabel")

    assert result == "Label_existing"
    service.users().labels().create.assert_not_called()


def test_get_or_create_label_creates_new():
    service = make_service()
    service.users().labels().create().execute.return_value = {
        "id": "Label_new",
        "name": "NewLabel",
    }
    lm = LabelManager(service)

    result = lm.get_or_create_label("NewLabel")

    assert result == "Label_new"
    assert lm._cache["NewLabel"] == "Label_new"


def test_get_or_create_label_nested_creates_parent():
    service = make_service()
    service.users().labels().create().execute.side_effect = [
        {"id": "Label_parent", "name": "AI-Sorted"},
        {"id": "Label_child", "name": "AI-Sorted/Work"},
    ]
    lm = LabelManager(service)

    result = lm.get_or_create_label("AI-Sorted/Work")

    assert result == "Label_child"
    assert "AI-Sorted" in lm._cache
    assert lm._cache["AI-Sorted"] == "Label_parent"


def test_get_or_create_label_409_refreshes_and_returns():
    service = MagicMock()
    # First list() returns empty; after 409 a second list returns the label.
    service.users().labels().list().execute.side_effect = [
        {"labels": []},
        {"labels": [{"name": "ExistingLabel", "id": "Label_409"}]},
    ]
    service.users().labels().create().execute.side_effect = make_http_error(409)

    lm = LabelManager(service)
    result = lm.get_or_create_label("ExistingLabel")

    assert result == "Label_409"


def test_get_or_create_label_409_not_in_cache_reraises():
    service = MagicMock()
    # After 409 the label is still not in the refreshed cache.
    service.users().labels().list().execute.return_value = {"labels": []}
    service.users().labels().create().execute.side_effect = make_http_error(409)

    lm = LabelManager(service)
    with pytest.raises(HttpError):
        lm.get_or_create_label("Ghost")


def test_get_or_create_label_non_409_reraises():
    service = make_service()
    service.users().labels().create().execute.side_effect = make_http_error(500)

    lm = LabelManager(service)
    with pytest.raises(HttpError):
        lm.get_or_create_label("AnyLabel")


# ---------------------------------------------------------------------------
# warm_cache
# ---------------------------------------------------------------------------

def test_warm_cache_creates_all_labels():
    service = make_service()
    service.users().labels().create().execute.side_effect = [
        {"id": "Label_1", "name": "Label1"},
        {"id": "Label_2", "name": "Label2"},
    ]
    lm = LabelManager(service)
    lm.warm_cache(["Label1", "Label2"])

    assert lm._cache["Label1"] == "Label_1"
    assert lm._cache["Label2"] == "Label_2"


def test_warm_cache_empty_list():
    service = make_service()
    lm = LabelManager(service)
    lm.warm_cache([])  # Should not raise


# ---------------------------------------------------------------------------
# _refresh_cache
# ---------------------------------------------------------------------------

def test_refresh_cache_populates():
    service = make_service(labels=[
        {"name": "INBOX", "id": "INBOX"},
        {"name": "AI-Sorted/Work", "id": "Label_999"},
    ])
    lm = LabelManager(service)
    lm._refresh_cache()

    assert lm._cache_populated is True
    assert lm._cache["INBOX"] == "INBOX"
    assert lm._cache["AI-Sorted/Work"] == "Label_999"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def make_gmail_service_with_labels():
    """Unused by tests directly; satisfies the parameter name."""
    pass
