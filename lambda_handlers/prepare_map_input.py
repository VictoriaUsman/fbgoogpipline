"""First state of `statemachine/ads_ingestion.asl.json`.

Expands `config/accounts.yaml` into a flat list of Step Functions Map items -- one per
account -- and computes each account's rolling lookback window via
`common.scheduling.scheduled_window`. All fan-out granularity decisions live here, not
in the state machine: the Map state just iterates whatever list this handler returns.

Input:  {"time": "<ISO-8601 EventBridge scheduled event time>"}
Output: {
    "items": [
        {
            "platform": "google_ads" | "meta_ads",
            "account_id": str,
            "account_name": str,
            "currency": str,
            "secret_name": str,
            "login_customer_id": str | None,
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD",
        },
        ...
    ]
}
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from common.logging_config import get_logger
from common.scheduling import scheduled_window

logger = get_logger(__name__)

ACCOUNTS_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "accounts.yaml"


def handler(event: dict, _context: Any = None) -> dict:
    event_time = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
    accounts = yaml.safe_load(ACCOUNTS_CONFIG_PATH.read_text())

    items = []
    for account in accounts:
        start_date, end_date = scheduled_window(event_time, account["platform"])
        items.append(
            {
                "platform": account["platform"],
                "account_id": account["account_id"],
                "account_name": account["account_name"],
                "currency": account["currency"],
                "secret_name": account["secret_name"],
                "login_customer_id": account.get("login_customer_id"),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )

    logger.info("prepared map input", extra={"fields": {"item_count": len(items)}})
    return {"items": items}
