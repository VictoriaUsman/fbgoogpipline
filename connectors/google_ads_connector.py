"""Google Ads API v17 connector -- Google Ads Query Language (GAQL) `search` reporting.

Unlike Amazon Ads / Meta Ads, the Google Ads API has no create-report / poll / download
lifecycle at all: `searchStream` (or paginated `search`) returns rows synchronously in
the same request/response cycle. That is the key architectural divergence this pipeline
has to absorb (see `statemachine/ads_ingestion.asl.json`'s `IsAsyncPlatform` Choice
state) -- Google Ads branches skip the Wait/Poll loop entirely and go straight from
"request" to "have rows in hand."

`query_campaign_performance()` intentionally does NOT implement the same
`create_report`/`poll_report` two-method interface `MetaAdsConnector` does; forcing a
shared abstract base class across a synchronous-query API and an async-report API would
mean one side implements no-op stubs for methods that don't apply to it. Both connectors
DO share `connectors/base.py`'s `RetryableSession` for HTTP retry/backoff, since that
part is genuinely identical regardless of fetch shape.

Auth: OAuth2 refresh-token grant (resolved by `common/secrets.py`) plus two
Google-Ads-specific headers on every call -- `developer-token` (issued once per Google
Ads manager account, not per advertiser) and `login-customer-id` (the MCC id used to
access a client account under it).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date

from common.logging_config import get_logger
from common.secrets import Credentials
from connectors.base import RetryableSession

logger = get_logger(__name__)

API_VERSION = "v17"
BASE_URL = f"https://googleads.googleapis.com/{API_VERSION}"

GAQL_CAMPAIGN_PERFORMANCE = """
    SELECT
        segments.date,
        campaign.id,
        campaign.name,
        campaign.advertising_channel_type,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions,
        metrics.conversions_value
    FROM campaign
    WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
"""


class GoogleAdsConnector:
    def __init__(self, *, customer_id: str, credentials: Credentials) -> None:
        self._customer_id = customer_id.replace("-", "")
        self._credentials = credentials
        self._session = RetryableSession()

    def query_campaign_performance(self, start_date: date, end_date: date) -> Iterator[dict]:
        """Run the campaign-performance GAQL query and yield one flattened dict per row.

        Synchronous end-to-end: by the time this generator is exhausted, every row for
        the window has already been fetched (paginated via `nextPageToken`, not streamed
        report chunks like the async platforms).
        """
        gaql = GAQL_CAMPAIGN_PERFORMANCE.format(start_date=start_date.isoformat(), end_date=end_date.isoformat())
        page_token: str | None = None
        while True:
            body: dict = {"query": gaql}
            if page_token:
                body["pageToken"] = page_token

            response = self._session.request(
                "POST",
                f"{BASE_URL}/customers/{self._customer_id}/googleAds:search",
                headers=self._headers(),
                data=json.dumps(body),
            )
            response.raise_for_status()
            payload = response.json()

            for row in payload.get("results", []):
                yield _flatten_row(row)

            page_token = payload.get("nextPageToken")
            if not page_token:
                return

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._credentials.access_token}",
            "Content-Type": "application/json",
        }
        if self._credentials.developer_token:
            headers["developer-token"] = self._credentials.developer_token
        if self._credentials.login_customer_id:
            headers["login-customer-id"] = self._credentials.login_customer_id.replace("-", "")
        return headers


def _flatten_row(row: dict) -> dict:
    campaign = row.get("campaign", {})
    metrics = row.get("metrics", {})
    segments = row.get("segments", {})
    cost_micros = int(metrics.get("costMicros", 0))
    return {
        "date": segments.get("date"),
        "campaign_id": str(campaign.get("id")),
        "campaign_name": campaign.get("name"),
        "channel_type": campaign.get("advertisingChannelType"),
        "impressions": int(metrics.get("impressions", 0)),
        "clicks": int(metrics.get("clicks", 0)),
        "cost": cost_micros / 1_000_000,
        "conversions": float(metrics.get("conversions", 0.0)),
        "conversions_value": float(metrics.get("conversionsValue", 0.0)),
    }
