"""Meta Ads-only poll-loop body in `statemachine/ads_ingestion.asl.json`: `Wait(30s)` ->
`ReportPoller` -> `Choice` (COMPLETED -> download, FAILED -> branch-fail, else -> back to
Wait), capped at 30 iterations before routing to `ReportTimedOut`. Google Ads items never
enter this loop -- they already carry `status: "COMPLETED"` out of `report_requester`.

Input:  {platform, account_id, account_name, currency, secret_name, report_run_id, poll_count}
Output: {platform, account_id, account_name, currency, secret_name, report_run_id,
         status: "IN_PROGRESS" | "COMPLETED" | "FAILED", poll_count}
"""

from __future__ import annotations

from typing import Any

from common.logging_config import get_logger
from common.secrets import get_credentials
from connectors.meta_ads_connector import MetaAdsConnector

logger = get_logger(__name__)

_STATUS_MAP = {
    "Job Completed": "COMPLETED",
    "Job Failed": "FAILED",
    "Job Skipped": "FAILED",
}


def handler(event: dict, _context: Any = None) -> dict:
    account_id = event["account_id"]
    credentials = get_credentials("meta_ads", event["secret_name"])
    connector = MetaAdsConnector(ad_account_id=account_id, credentials=credentials)

    report_status = connector.poll_report(event["report_run_id"])
    status = _STATUS_MAP.get(report_status.status, "IN_PROGRESS")

    logger.info(
        "polled meta ads report",
        extra={"fields": {"account_id": account_id, "status": status, "poll_count": event["poll_count"]}},
    )
    return {
        "platform": "meta_ads",
        "account_id": account_id,
        "account_name": event["account_name"],
        "currency": event["currency"],
        "secret_name": event["secret_name"],
        "report_run_id": event["report_run_id"],
        "status": status,
        "poll_count": event["poll_count"] + 1,
    }
