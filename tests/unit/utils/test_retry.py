"""Unit tests for retry utility helpers."""

from __future__ import annotations

import pytest

from gmail_sorter.utils.retry import with_retry


@pytest.mark.asyncio
async def test_with_retry_retries_and_uses_exponential_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry decorator should retry failures and back off exponentially."""

    attempts = {"count": 0}
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("gmail_sorter.utils.retry.asyncio.sleep", fake_sleep)

    @with_retry(max_retries=3, base_delay=1.0, max_delay=60.0, jitter=False)
    async def flaky_operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 4:
            raise RuntimeError("transient failure")
        return "ok"

    result = await flaky_operation()

    assert result == "ok"
    assert attempts["count"] == 4
    assert delays == [1.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_with_retry_reraises_after_retries_exhausted() -> None:
    """The final exception should propagate once retries are exhausted."""

    @with_retry(max_retries=2, base_delay=0.0, max_delay=0.0, jitter=False)
    async def always_fails() -> None:
        raise ValueError("permanent failure")

    with pytest.raises(ValueError, match="permanent failure"):
        await always_fails()


@pytest.mark.asyncio
async def test_with_retry_sets_retry_attempts_on_final_exception() -> None:
    """Final propagated exception should include retry-attempt metadata."""

    @with_retry(max_retries=2, base_delay=0.0, max_delay=0.0, jitter=False)
    async def always_fails() -> None:
        raise ValueError("permanent failure")

    with pytest.raises(ValueError) as exc_info:
        await always_fails()

    assert getattr(exc_info.value, "retry_attempts", None) == 3
