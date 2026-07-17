"""Per-Map-branch entrypoint of `statemachine/ads_ingestion.asl.json`, invoked once per
account returned by `prepare_map_input`.

This is the one place the two platforms' divergent fetch shapes actually surface in
Lambda code: Google Ads has no report lifecycle to kick off, so this handler runs the
GAQL query and writes bronze/ immediately, completing synchronously. Meta Ads only
*starts* an async report run here; `report_poller` and `report_downloader` finish the
job in later states. The state machine's `IsAsyncPlatform` Choice state (keyed on this
handler's `status` field) is what decides whether to enter the Wait/Poll loop or skip
straight past it.

Input:  {platform, account_id, account_name, currency, secret_name, login_customer_id, start_date, end_date}
Output (google_ads): {platform, account_id, status: "COMPLETED", rows_written}
Output (meta_ads):   {platform, account_id, account_name, currency, secret_name, status: "IN_PROGRESS",
                      report_run_id, poll_count: 0}
"""

from __future__ import annotations

from datetime import date
from typing import Any

from common.bronze_writer import write_bronze_ndjson
from common.logging_config import get_logger
from common.secrets import get_credentials
from connectors.google_ads_connector import GoogleAdsConnector
from connectors.meta_ads_connector import MetaAdsConnector

logger = get_logger(__name__)


def handler(event: dict, _context: Any = None) -> dict:
    platform = event["platform"]
    account_id = event["account_id"]
    start_date = date.fromisoformat(event["start_date"])
    end_date = date.fromisoformat(event["end_date"])
    credentials = get_credentials(platform, event["secret_name"])

    if platform == "google_ads":
        credentials = _with_google_ads_headers(credentials, event.get("login_customer_id"))
        connector = GoogleAdsConnector(customer_id=account_id, credentials=credentials)
        rows = _enrich_rows(connector.query_campaign_performance(start_date, end_date), event)
        rows_written = write_bronze_ndjson(rows, platform=platform, account_id=account_id)
        logger.info("google ads request completed synchronously", extra={"fields": {"account_id": account_id}})
        return {"platform": platform, "account_id": account_id, "status": "COMPLETED", "rows_written": rows_written}

    if platform == "meta_ads":
        connector = MetaAdsConnector(ad_account_id=account_id, credentials=credentials)
        report_run_id = connector.create_report(start_date, end_date)
        logger.info(
            "meta ads report requested",
            extra={"fields": {"account_id": account_id, "report_run_id": report_run_id}},
        )
        return {
            "platform": platform,
            "account_id": account_id,
            "account_name": event["account_name"],
            "currency": event["currency"],
            "secret_name": event["secret_name"],
            "status": "IN_PROGRESS",
            "report_run_id": report_run_id,
            "poll_count": 0,
        }

    raise ValueError(f"unknown platform {platform!r}")


def _with_google_ads_headers(credentials, login_customer_id: str | None):
    from dataclasses import replace

    return replace(credentials, developer_token="demo-developer-token", login_customer_id=login_customer_id)


def _enrich_rows(rows, event: dict):
    """Attach account-level fields the connector itself has no reason to know about
    (it only knows the account id it was pointed at) so each bronze record is
    self-describing for the Glue validation step and the warehouse load."""
    for row in rows:
        yield {
            **row,
            "platform": event["platform"],
            "account_id": event["account_id"],
            "account_name": event["account_name"],
            "currency": event["currency"],
        }
