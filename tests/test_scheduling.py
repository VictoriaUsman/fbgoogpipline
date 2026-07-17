from datetime import date, datetime

import pytest

from common.scheduling import date_range, scheduled_window


def test_scheduled_window_google_ads_is_seven_day_lookback_ending_yesterday():
    event_time = datetime.fromisoformat("2026-07-17T06:00:00+00:00")
    start, end = scheduled_window(event_time, "google_ads")
    assert end == date(2026, 7, 16)
    assert start == date(2026, 7, 10)
    assert (end - start).days == 6  # 7 inclusive days


def test_scheduled_window_meta_ads_is_seven_day_lookback_ending_yesterday():
    event_time = datetime.fromisoformat("2026-07-17T06:00:00+00:00")
    start, end = scheduled_window(event_time, "meta_ads")
    assert end == date(2026, 7, 16)
    assert start == date(2026, 7, 10)


def test_scheduled_window_unknown_platform_raises():
    with pytest.raises(ValueError, match="unknown platform"):
        scheduled_window(datetime.fromisoformat("2026-07-17T06:00:00+00:00"), "tiktok_ads")


def test_scheduled_window_is_anchored_on_event_time_not_wallclock():
    # A manual re-run for a past scheduled event must reproduce the exact same window.
    event_time = datetime.fromisoformat("2026-01-05T06:00:00+00:00")
    assert scheduled_window(event_time, "google_ads") == (date(2025, 12, 29), date(2026, 1, 4))


def test_date_range_is_inclusive():
    assert date_range(date(2026, 7, 1), date(2026, 7, 3)) == [
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
    ]


def test_date_range_single_day():
    assert date_range(date(2026, 7, 1), date(2026, 7, 1)) == [date(2026, 7, 1)]


def test_date_range_rejects_backwards_range():
    with pytest.raises(ValueError, match="end_date must be on or after start_date"):
        date_range(date(2026, 7, 3), date(2026, 7, 1))
