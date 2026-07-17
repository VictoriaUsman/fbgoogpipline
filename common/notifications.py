"""Microsoft Teams incoming-webhook alerting for reconciliation mismatches and
data-quality threshold breaches (see `local_runner/run_pipeline.py`).

Mirrors `common/secrets.py`'s DEMO_MODE pattern: this demo project has no real Teams
channel to post to, so DEMO_MODE=1 (the default) -- or simply not configuring
TEAMS_WEBHOOK_URL -- logs exactly what would have been sent instead of making a real
HTTP call. Callers never need to branch on DEMO_MODE themselves; `send_teams_alert`
always returns whether it actually posted over the network.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from common.logging_config import get_logger

logger = get_logger(__name__)

DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

_REQUEST_TIMEOUT_SECONDS = 10


def send_teams_alert(title: str, text: str, *, facts: dict[str, Any] | None = None) -> bool:
    """Post an Office 365 Connector "MessageCard" to `TEAMS_WEBHOOK_URL`.

    Returns True only if a real HTTP POST was made. In DEMO_MODE (default) or without
    TEAMS_WEBHOOK_URL configured, logs the alert at WARNING and returns False -- this
    never raises just because alerting isn't wired up to a real channel.
    """
    if DEMO_MODE or not TEAMS_WEBHOOK_URL:
        logger.warning(
            "teams alert not sent (DEMO_MODE or no TEAMS_WEBHOOK_URL configured)",
            extra={"fields": {"title": title, "text": text, **(facts or {})}},
        )
        return False

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": title,
        "themeColor": "C0392B",
        "title": title,
        "text": text,
        "sections": [{"facts": [{"name": k, "value": str(v)} for k, v in facts.items()]}] if facts else [],
    }
    response = requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=_REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    logger.info("teams alert sent", extra={"fields": {"title": title}})
    return True
