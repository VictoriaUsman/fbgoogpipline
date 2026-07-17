from datetime import date

import pytest

from common.s3_paths import object_key, swap_zone


def test_object_key_builds_hive_style_partitioned_path():
    key = object_key("bronze", platform="google_ads", account_id="111-222-3333", report_date=date(2026, 7, 3))
    assert key == (
        "bronze/platform=google_ads/account_id=111-222-3333/"
        "year=2026/month=07/day=03/report_part0000.json"
    )


def test_object_key_part_number_is_zero_padded():
    key = object_key("bronze", platform="meta_ads", account_id="act_1", report_date=date(2026, 7, 3), part=7)
    assert key.endswith("report_part0007.json")


def test_object_key_rejects_unknown_zone():
    with pytest.raises(ValueError, match="unknown zone"):
        object_key("gold", platform="google_ads", account_id="1", report_date=date(2026, 7, 3))


def test_swap_zone_preserves_partition_segments():
    bronze_key = object_key("bronze", platform="google_ads", account_id="111-222-3333", report_date=date(2026, 7, 3))
    rejected_key = swap_zone(bronze_key, "rejected")
    assert rejected_key == (
        "rejected/platform=google_ads/account_id=111-222-3333/"
        "year=2026/month=07/day=03/report_part0000.json"
    )


def test_swap_zone_rejects_unknown_zone():
    bronze_key = object_key("bronze", platform="google_ads", account_id="1", report_date=date(2026, 7, 3))
    with pytest.raises(ValueError, match="unknown zone"):
        swap_zone(bronze_key, "gold")
