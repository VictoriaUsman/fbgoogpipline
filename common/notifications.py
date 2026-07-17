"""Microsoft Teams incoming-webhook alerting for reconciliation mismatches and
data-quality threshold breaches (see `local_runner/run_pipeline.py`).

Gated on TEAMS_WEBHOOK_URL alone, deliberately NOT on the project-wide DEMO_MODE flag
(see `common/secrets.py`) -- DEMO_MODE also controls whether credential resolution is
stubbed, and flipping it off just to get real Teams alerts would send the rest of the
pipeline looking for real ad-account credentials that don't exist here. Not configuring
TEAMS_WEBHOOK_URL logs exactly what would have been sent instead of making a real HTTP
call. Callers never need to branch on this themselves; `send_teams_alert` always
returns whether it actually posted over the network.
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

    Returns True only if a real HTTP POST was made. Without TEAMS_WEBHOOK_URL
    configured, logs the alert at WARNING and returns False -- this never raises just
    because alerting isn't wired up to a real channel.
    """
    if not TEAMS_WEBHOOK_URL:
        logger.warning(
            "teams alert not sent (no TEAMS_WEBHOOK_URL configured)",
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
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=_REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        # A broken or unreachable webhook (wrong URL, channel connector removed, network
        # blip) must never fail the pipeline run over a missed notification -- log it and
        # move on exactly like the DEMO_MODE path above.
        logger.error(
            "teams alert failed to send",
            extra={"fields": {"title": title, "error": str(exc)}},
        )
        return False

    logger.info("teams alert sent", extra={"fields": {"title": title}})
    return True
