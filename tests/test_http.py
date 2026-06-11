from __future__ import annotations

import urllib.error

import pytest

import policyengine_bundles.http as http
from policyengine_bundles.http import request_with_retries


def test_request_with_retries_retries_retryable_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    attempts = 0

    def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise urllib.error.HTTPError(
                url="https://example.test/data.json",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "0"},
                fp=None,
            )
        return "ok"

    monkeypatch.setattr(http.time, "sleep", fake_sleep)

    assert request_with_retries(operation) == "ok"
    assert attempts == 2
    assert sleeps == [0.0]


def test_request_with_retries_does_not_retry_nonretryable_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        raise urllib.error.HTTPError(
            url="https://example.test/data.json",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

    monkeypatch.setattr(http.time, "sleep", sleeps.append)

    with pytest.raises(urllib.error.HTTPError):
        request_with_retries(operation)
    assert attempts == 1
    assert sleeps == []


def test_request_with_retries_retries_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("timed out")
        return "ok"

    monkeypatch.setattr(http.time, "sleep", sleeps.append)

    assert request_with_retries(operation) == "ok"
    assert attempts == 2
    assert sleeps == [2.0]
