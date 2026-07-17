import json
from datetime import date

import pytest

from common.bronze_writer import write_bronze_ndjson
from common.s3_paths import object_key
from glue_jobs.bronze_to_silver import _list_bronze_keys, main


@pytest.fixture(autouse=True)
def isolated_lake_root(tmp_path, monkeypatch):
    import common.s3_paths as s3_paths

    monkeypatch.setattr(s3_paths, "LAKE_ROOT", tmp_path)
    return tmp_path


VALID_ROW = {
    "date": "2026-07-03",
    "platform": "google_ads",
    "account_id": "111-222-3333",
    "account_name": "Acme Retail",
    "currency": "USD",
    "campaign_id": "7001001",
    "campaign_name": "Search - Brand",
    "impressions": 1000,
    "clicks": 50,
    "cost": 123.45,
    "conversions": 4.0,
}

INVALID_ROW = {**VALID_ROW, "cost": -5.0}


def _argv(lake_root):
    return [
        "bronze_to_silver.py",
        "--bucket",
        str(lake_root),
        "--start-date",
        "2026-07-01",
        "--until-date",
        "2026-07-31",
    ]


def test_list_bronze_keys_filters_by_date_window(isolated_lake_root):
    write_bronze_ndjson([VALID_ROW], platform="google_ads", account_id="111-222-3333")
    write_bronze_ndjson(
        [{**VALID_ROW, "date": "2026-08-01"}], platform="google_ads", account_id="111-222-3333"
    )

    keys = _list_bronze_keys(isolated_lake_root, date(2026, 7, 1), date(2026, 7, 31))
    assert len(keys) == 1
    assert "day=03" in keys[0]


def test_main_splits_valid_and_rejected_records(isolated_lake_root, monkeypatch):
    write_bronze_ndjson([VALID_ROW, INVALID_ROW], platform="google_ads", account_id="111-222-3333")

    monkeypatch.setattr("sys.argv", _argv(isolated_lake_root))
    main()

    silver_key = object_key(
        "silver", platform="google_ads", account_id="111-222-3333", report_date=date(2026, 7, 3)
    )
    rejected_key = object_key(
        "rejected", platform="google_ads", account_id="111-222-3333", report_date=date(2026, 7, 3)
    )

    silver_rows = [json.loads(line) for line in (isolated_lake_root / silver_key).read_text().splitlines()]
    rejected_rows = [json.loads(line) for line in (isolated_lake_root / rejected_key).read_text().splitlines()]

    assert len(silver_rows) == 1
    assert silver_rows[0]["campaign_id"] == "7001001"

    assert len(rejected_rows) == 1
    assert rejected_rows[0]["_validation_error"] == "field cost is negative: -5.0"


def test_main_with_no_bronze_files_writes_nothing(isolated_lake_root, monkeypatch):
    monkeypatch.setattr("sys.argv", _argv(isolated_lake_root))
    main()  # must not raise even though bronze/ doesn't exist yet
    assert not (isolated_lake_root / "silver").exists()
    assert not (isolated_lake_root / "rejected").exists()


def test_main_detects_schema_drift_without_rejecting(isolated_lake_root, monkeypatch):
    # get_logger() caches a module-singleton logger whose handler's stdout reference
    # predates pytest's per-test capture fixtures (see the analogous note in
    # test_connectors.py) -- spy on the module's logger.warning directly instead.
    import glue_jobs.bronze_to_silver as bronze_to_silver_module

    warnings = []
    monkeypatch.setattr(
        bronze_to_silver_module.logger, "warning", lambda msg, **kwargs: warnings.append((msg, kwargs))
    )

    drifted_row = {**VALID_ROW, "audience_segment": "lookalike-1pct"}
    write_bronze_ndjson([drifted_row], platform="google_ads", account_id="111-222-3333")

    monkeypatch.setattr("sys.argv", _argv(isolated_lake_root))
    main()

    silver_key = object_key(
        "silver", platform="google_ads", account_id="111-222-3333", report_date=date(2026, 7, 3)
    )
    silver_rows = [json.loads(line) for line in (isolated_lake_root / silver_key).read_text().splitlines()]
    assert len(silver_rows) == 1  # drift is a signal, not a rejection

    assert len(warnings) == 1
    message, kwargs = warnings[0]
    assert message == "schema drift detected"
    assert kwargs["extra"]["fields"]["field"] == "audience_segment"
