"""Idempotent rolling-window date math, anchored on the EventBridge scheduled event time
rather than wall-clock `date.today()` -- so a manually re-run execution for a past date
produces the exact same window as the original scheduled run, and downstream S3 keys
(built from `report_date`, see `common/s3_paths.py`) overwrite instead of duplicating.

The lookback window is platform-specific because it exists to catch *late-arriving
conversions*, not raw click/impression data (those are final same-day). Rationale:

- Google Ads: default conversion attribution window is commonly configured up to 30
  days for click-through conversions, so a 7-day rolling lookback re-pulls the days most
  likely to have shifted since yesterday's run without re-pulling the full 30 days daily.
- Meta Ads: default attribution setting is 7-day-click / 1-day-view, so a matching 7-day
  lookback is used here too -- unlike the Amazon Ads reference pipeline's 30-day window,
  which exists for a different reason (delayed order/return reconciliation on Amazon's
  side, not ad-attribution lag).

Both platforms therefore use the same constant today, but the two constants are kept
separate below (not aliased) since the two platforms' attribution settings are configured
independently per account and can diverge.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

LOOKBACK_DAYS_BY_PLATFORM = {
    "google_ads": 7,
    "meta_ads": 7,
}


def scheduled_window(event_time: datetime, platform: str) -> tuple[date, date]:
    """Return the inclusive (start_date, end_date) window to (re-)pull for `platform`.

    `end_date` is always the day before `event_time` (yesterday, relative to the
    scheduled run) since same-day data is still accruing. `start_date` walks back
    `LOOKBACK_DAYS_BY_PLATFORM[platform]` additional days to re-capture late-arriving
    conversion data.
    """
    if platform not in LOOKBACK_DAYS_BY_PLATFORM:
        raise ValueError(f"unknown platform {platform!r}")
    end_date = event_time.date() - timedelta(days=1)
    start_date = end_date - timedelta(days=LOOKBACK_DAYS_BY_PLATFORM[platform] - 1)
    return start_date, end_date


def date_range(start_date: date, end_date: date) -> list[date]:
    """Enumerate every date in an inclusive [start_date, end_date] range."""
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    days = (end_date - start_date).days
    return [start_date + timedelta(days=offset) for offset in range(days + 1)]
