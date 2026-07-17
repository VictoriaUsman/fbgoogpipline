"""Shared HTTP retry/backoff wrapper used by every connector, regardless of source
platform or fetch shape.

Google Ads and Meta Ads differ enough in their actual fetch pattern that they do not
share a single abstract create/poll/download interface (see module docstrings on
`google_ads_connector.py` and `meta_ads_connector.py` for why). What they DO share --
and what actually deserves to live in one place -- is retry-on-transient-failure HTTP
semantics: same status codes worth retrying, same Retry-After handling, same jittered
exponential backoff shape, same attempt cap. `RetryableSession._request` is that one
place; both connectors compose it rather than subclassing a fetch-shaped ABC that would
have to be violated by one of them.
"""

from __future__ import annotations

import random
import time
from typing import Any

import requests

from common.logging_config import get_logger

logger = get_logger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5


class PlatformApiError(RuntimeError):
    """Raised when a platform API call fails after exhausting all retry attempts."""


class RetryableSession:
    """Thin wrapper around `requests` adding retry/backoff for transient failures.

    Not a connector base class -- composed by both `GoogleAdsConnector` and
    `MetaAdsConnector` via `self._session = RetryableSession()` so retry behavior stays
    identical across platforms without forcing a shared fetch-shape ABC.
    """

    def __init__(self, *, max_attempts: int = MAX_ATTEMPTS) -> None:
        self._max_attempts = max_attempts

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = requests.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                self._sleep_before_retry(attempt, retry_after=None)
                continue

            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response

            if attempt == self._max_attempts:
                response.raise_for_status()

            retry_after = response.headers.get("Retry-After")
            logger.warning(
                "retryable HTTP status, backing off",
                extra={"fields": {"status_code": response.status_code, "attempt": attempt, "url": url}},
            )
            self._sleep_before_retry(attempt, retry_after=retry_after)

        raise PlatformApiError(f"exhausted {self._max_attempts} attempts calling {url}") from last_exc

    @staticmethod
    def _sleep_before_retry(attempt: int, *, retry_after: str | None) -> None:
        if retry_after is not None:
            try:
                time.sleep(float(retry_after))
                return
            except ValueError:
                pass
        time.sleep(random.uniform(0, min(60, 2**attempt)))
