"""Meta Marketing API connector -- async Insights report, the same create/poll/download
shape as the Amazon Ads reference pipeline this project's architecture is based on.

Fetch pattern: `POST /{ad_account}/insights?async=true` kicks off a background report
run and returns a `report_run_id`; the caller polls `GET /{report_run_id}` until
`async_status` reaches `Job Completed`, then pages through `GET /{report_run_id}/insights`
(cursor pagination via `paging.cursors.after`) to retrieve rows. This is why
`MetaAdsConnector` keeps the `create_report` / `poll_report` two-method shape the
Amazon connector used -- unlike Google Ads, this genuinely is an async job.

Auth: a long-lived Meta System User access token (resolved by `common/secrets.py`),
passed as a query parameter (Meta's convention, not a Bearer header) on every call.

Rate limiting: Meta reports usage via the `X-Business-Use-Case-Usage` response header
(a JSON blob per ad account with `call_count`/`total_cputime`/`total_time` as
percentages of the account's quota) rather than a bare `Retry-After` -- this connector
logs a warning once usage crosses 80% so throttling is visible before Meta starts
returning 429s, which `connectors/base.py`'s `RetryableSession` will still back off from
on its own.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from common.logging_config import get_logger
from common.secrets import Credentials
from connectors.base import RetryableSession

logger = get_logger(__name__)

API_VERSION = "v19.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

USAGE_WARNING_THRESHOLD_PCT = 80

FIELDS = (
    "date_start",
    "campaign_id",
    "campaign_name",
    "impressions",
    "clicks",
    "spend",
    "actions",
    "action_values",
)

TERMINAL_STATUSES = {"Job Completed", "Job Failed", "Job Skipped"}


@dataclass(frozen=True)
class ReportStatus:
    status: str
    percent_complete: int
    failure_reason: str | None = None


class MetaAdsConnector:
    def __init__(self, *, ad_account_id: str, credentials: Credentials) -> None:
        self._ad_account_id = ad_account_id
        self._credentials = credentials
        self._session = RetryableSession()

    def create_report(self, start_date: date, end_date: date) -> str:
        """Kick off an async Insights report run; returns the `report_run_id` to poll."""
        response = self._session.request(
            "POST",
            f"{BASE_URL}/{self._ad_account_id}/insights",
            params={
                "access_token": self._credentials.access_token,
                "level": "campaign",
                "fields": json.dumps(list(FIELDS)),
                "time_range": json.dumps({"since": start_date.isoformat(), "until": end_date.isoformat()}),
                "time_increment": 1,  # one row per campaign per day, not one aggregate row for the whole range
                "async": "true",
            },
        )
        response.raise_for_status()
        self._log_usage_if_high(response)
        return response.json()["report_run_id"]

    def poll_report(self, report_run_id: str) -> ReportStatus:
        """Check the status of a previously created report run."""
        response = self._session.request(
            "GET",
            f"{BASE_URL}/{report_run_id}",
            params={"access_token": self._credentials.access_token},
        )
        response.raise_for_status()
        self._log_usage_if_high(response)
        payload = response.json()
        return ReportStatus(
            status=payload.get("async_status", "Unknown"),
            percent_complete=int(payload.get("async_percent_completion", 0)),
        )

    def download_report(self, report_run_id: str) -> Iterator[dict]:
        """Page through a completed report's rows via cursor pagination and flatten each one."""
        url = f"{BASE_URL}/{report_run_id}/insights"
        params: dict = {"access_token": self._credentials.access_token, "limit": 500}
        while True:
            response = self._session.request("GET", url, params=params)
            response.raise_for_status()
            self._log_usage_if_high(response)
            payload = response.json()

            for row in payload.get("data", []):
                yield _flatten_row(row)

            next_url = payload.get("paging", {}).get("next")
            if not next_url:
                return
            url, params = next_url, {}

    def _log_usage_if_high(self, response) -> None:
        usage_header = response.headers.get("X-Business-Use-Case-Usage")
        if not usage_header:
            return
        try:
            usage = json.loads(usage_header)
        except json.JSONDecodeError:
            return
        for entries in usage.values():
            for entry in entries:
                worst = max(entry.get("call_count", 0), entry.get("total_cputime", 0), entry.get("total_time", 0))
                if worst >= USAGE_WARNING_THRESHOLD_PCT:
                    logger.warning(
                        "approaching Meta rate limit",
                        extra={"fields": {"ad_account_id": self._ad_account_id, "usage_pct": worst}},
                    )


def _flatten_row(row: dict) -> dict:
    return {
        "date": row.get("date_start"),
        "campaign_id": row.get("campaign_id"),
        "campaign_name": row.get("campaign_name"),
        "impressions": int(row.get("impressions", 0)),
        "clicks": int(row.get("clicks", 0)),
        "cost": float(row.get("spend", 0.0)),
        "conversions": _sum_action_field(row.get("actions"), "offsite_conversion.fb_pixel_purchase"),
        "conversions_value": _sum_action_field(row.get("action_values"), "offsite_conversion.fb_pixel_purchase"),
    }


def _sum_action_field(actions: list[dict] | None, action_type: str) -> float:
    if not actions:
        return 0.0
    return sum(float(a["value"]) for a in actions if a.get("action_type") == action_type)
