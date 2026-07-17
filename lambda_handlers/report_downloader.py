"""Meta Ads-only final state of the per-account branch in `statemachine/ads_ingestion.asl.json`,
reached once `report_poller` reports `status: "COMPLETED"`. Streams the finished report's
rows into bronze/ via the same writer Google Ads' synchronous path uses.

Input:  {platform, account_id, account_name, currency, secret_name, report_run_id}
Output: {platform, account_id, status: "COMPLETED", rows_written}
"""

from __future__ import annotations

from typing import Any

from common.bronze_writer import write_bronze_ndjson
from common.logging_config import get_logger
from common.secrets import get_credentials
from connectors.meta_ads_connector import MetaAdsConnector

logger = get_logger(__name__)


def handler(event: dict, _context: Any = None) -> dict:
    account_id = event["account_id"]
    credentials = get_credentials("meta_ads", event["secret_name"])
    connector = MetaAdsConnector(ad_account_id=account_id, credentials=credentials)

    rows = _enrich_rows(connector.download_report(event["report_run_id"]), event)
    rows_written = write_bronze_ndjson(rows, platform="meta_ads", account_id=account_id)

    logger.info("meta ads report downloaded", extra={"fields": {"account_id": account_id}})
    return {"platform": "meta_ads", "account_id": account_id, "status": "COMPLETED", "rows_written": rows_written}


def _enrich_rows(rows, event: dict):
    """Attach account-level fields (see report_requester._enrich_rows for why)."""
    for row in rows:
        yield {
            **row,
            "platform": event["platform"],
            "account_id": event["account_id"],
            "account_name": event["account_name"],
            "currency": event["currency"],
        }
