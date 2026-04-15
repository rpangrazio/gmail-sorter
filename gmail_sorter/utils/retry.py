"""Retry and backoff helpers used by external service clients."""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

LOGGER = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _calculate_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter: bool,
) -> float:
    """Calculate retry delay using exponential backoff with optional jitter."""

    delay = min(base_delay * (2**attempt), max_delay)
    if jitter:
        delay += random.random()
    return delay


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Wrap a function with retry behavior.

    The decorator supports both synchronous and asynchronous callables.
    """

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except retryable_exceptions as exc:
                        if attempt == max_retries:
                            raise

                        LOGGER.warning(
                            "Retrying after failure (attempt %s/%s): %s",
                            attempt + 1,
                            max_retries,
                            exc,
                        )
                        await asyncio.sleep(
                            _calculate_delay(
                                attempt=attempt,
                                base_delay=base_delay,
                                max_delay=max_delay,
                                jitter=jitter,
                            )
                        )

                raise RuntimeError("Retry loop exited unexpectedly.")

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    if attempt == max_retries:
                        raise

                    LOGGER.warning(
                        "Retrying after failure (attempt %s/%s): %s",
                        attempt + 1,
                        max_retries,
                        exc,
                    )
                    time.sleep(
                        _calculate_delay(
                            attempt=attempt,
                            base_delay=base_delay,
                            max_delay=max_delay,
                            jitter=jitter,
                        )
                    )

            raise RuntimeError("Retry loop exited unexpectedly.")

        return sync_wrapper  # type: ignore[return-value]

    return decorator
