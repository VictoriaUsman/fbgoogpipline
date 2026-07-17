"""OAuth credential resolution for both platforms, with in-process caching.

Real refresh tokens / system-user tokens never live in `config/accounts.yaml` -- that
file only carries a `secret_name` pointer (see `config/accounts.example.yaml`). In
production this module resolves that pointer via `boto3.client("secretsmanager")`. In
this demo project nothing is deployed and no real ad-account credentials exist, so
`DEMO_MODE=1` (the default) short-circuits credential resolution to a fixed stub value
-- the connectors never see the difference, since both paths return the same shape.

Never log a resolved token. Auth failures re-raise with `from None` to strip any
chained traceback that might otherwise carry a credential fragment into CloudWatch Logs.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from common.logging_config import get_logger

logger = get_logger(__name__)

DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_TTL_SECONDS = 3300  # refresh a few minutes before a typical 1hr access-token expiry


@dataclass(frozen=True)
class Credentials:
    access_token: str
    developer_token: str | None = None  # Google Ads only
    login_customer_id: str | None = None  # Google Ads only, MCC id


def get_credentials(platform: str, secret_name: str) -> Credentials:
    """Resolve short-lived credentials for `secret_name`, cached until near expiry."""
    cached = _TOKEN_CACHE.get(secret_name)
    if cached and cached[1] > time.monotonic():
        return Credentials(access_token=cached[0])

    try:
        if DEMO_MODE:
            token = f"demo-token::{secret_name}"
        elif platform == "google_ads":
            token = _refresh_google_ads_token(secret_name)
        elif platform == "meta_ads":
            token = _resolve_meta_system_user_token(secret_name)
        else:
            raise ValueError(f"unknown platform {platform!r}")
    except Exception:  # noqa: BLE001 - intentionally broad, re-raised stripped below
        logger.error("credential resolution failed", extra={"fields": {"secret_name": secret_name}})
        raise RuntimeError(f"could not resolve credentials for {secret_name}") from None

    _TOKEN_CACHE[secret_name] = (token, time.monotonic() + _TOKEN_TTL_SECONDS)
    return Credentials(access_token=token)


def _refresh_google_ads_token(secret_name: str) -> str:
    """Exchange a stored OAuth2 refresh token for a short-lived access token (production only)."""
    raise NotImplementedError("real Google OAuth2 token exchange is out of scope for this demo project")


def _resolve_meta_system_user_token(secret_name: str) -> str:
    """Fetch a long-lived Meta System User access token from Secrets Manager (production only)."""
    raise NotImplementedError("real Meta System User token retrieval is out of scope for this demo project")
