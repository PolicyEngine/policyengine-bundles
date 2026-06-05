from __future__ import annotations

import email.utils
import time
import urllib.error
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

T = TypeVar("T")

RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}


def request_with_retries(
    operation: Callable[[], T],
    *,
    attempts: int = 5,
    initial_delay_seconds: float = 2.0,
    max_delay_seconds: float = 30.0,
) -> T:
    """Run a URL operation with bounded retries for transient failures."""

    if attempts < 1:
        raise ValueError("attempts must be at least 1.")

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_STATUS_CODES or attempt == attempts:
                raise
            time.sleep(
                _retry_delay_seconds(
                    exc,
                    attempt=attempt,
                    initial_delay_seconds=initial_delay_seconds,
                    max_delay_seconds=max_delay_seconds,
                )
            )
        except urllib.error.URLError:
            if attempt == attempts:
                raise
            time.sleep(
                min(
                    initial_delay_seconds * (2 ** (attempt - 1)),
                    max_delay_seconds,
                )
            )
        except TimeoutError:
            if attempt == attempts:
                raise
            time.sleep(
                min(
                    initial_delay_seconds * (2 ** (attempt - 1)),
                    max_delay_seconds,
                )
            )

    raise RuntimeError("URL retry loop exited unexpectedly.")


def _retry_delay_seconds(
    error: urllib.error.HTTPError,
    *,
    attempt: int,
    initial_delay_seconds: float,
    max_delay_seconds: float,
) -> float:
    headers = error.headers or {}
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), max_delay_seconds)
        except ValueError:
            try:
                parsed = email.utils.parsedate_to_datetime(retry_after)
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                delay = (parsed - datetime.now(UTC)).total_seconds()
                return min(max(delay, 0.0), max_delay_seconds)
    return min(initial_delay_seconds * (2 ** (attempt - 1)), max_delay_seconds)
