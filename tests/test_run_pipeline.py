import json
import sqlite3
from datetime import date

import pytest

import common.s3_paths as s3_paths
import local_runner.run_pipeline as run_pipeline
from common.bronze_writer import write_bronze_ndjson


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    lake_root = tmp_path / "data_lake"
    monkeypatch.setattr(s3_paths, "LAKE_ROOT", lake_root)
    monkeypatch.setattr(run_pipeline, "LAKE_ROOT", lake_root)
    monkeypatch.setattr(run_pipeline, "WAREHOUSE_DB_PATH", tmp_path / "warehouse" / "pipeline.db")
    monkeypatch.setattr(run_pipeline, "SNAPSHOT_DIR", tmp_path / "warehouse" / "snapshots")
    monkeypatch.setattr(run_pipeline, "DASHBOARD_DATA_DIR", tmp_path / "dashboard_data")
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


def test_run_glue_transform_returns_rejected_ratio_summary(isolated_paths):
    write_bronze_ndjson([VALID_ROW, INVALID_ROW], platform="google_ads", account_id="111-222-3333")

    data_quality = run_pipeline.run_glue_transform(date(2026, 7, 1), date(2026, 7, 31))

    assert data_quality["rejected_ratios"]["google_ads"] == pytest.approx(0.5)
    assert data_quality["drift_fields"] == {}


def test_run_glue_transform_reports_schema_drift(isolated_paths):
    drifted_row = {**VALID_ROW, "audience_segment": "lookalike_1pct"}
    write_bronze_ndjson([drifted_row], platform="google_ads", account_id="111-222-3333")

    data_quality = run_pipeline.run_glue_transform(date(2026, 7, 1), date(2026, 7, 31))

    assert data_quality["rejected_ratios"]["google_ads"] == 0.0
    assert data_quality["drift_fields"] == {"google_ads.audience_segment": 1}


def test_snapshot_warehouse_writes_a_point_in_time_copy(isolated_paths):
    conn = run_pipeline.init_warehouse()
    conn.execute(
        "INSERT INTO dim_account (account_id, platform, account_name, currency, valid_from, is_current) "
        "VALUES ('a1', 'google_ads', 'Acme', 'USD', '2026-07-01T00:00:00+00:00', 1)"
    )
    conn.commit()

    snapshot_path = run_pipeline.snapshot_warehouse(conn, "2026-07-17T05:15:23.456789+00:00")

    assert snapshot_path.exists()
    assert snapshot_path.parent == isolated_paths / "warehouse" / "snapshots"

    snapshot_conn = sqlite3.connect(snapshot_path)
    row = snapshot_conn.execute("SELECT account_id FROM dim_account").fetchone()
    snapshot_conn.close()
    assert row == ("a1",)


def test_snapshot_warehouse_is_unaffected_by_later_writes_to_the_live_db(isolated_paths):
    conn = run_pipeline.init_warehouse()
    conn.execute(
        "INSERT INTO dim_account (account_id, platform, account_name, currency, valid_from, is_current) "
        "VALUES ('a1', 'google_ads', 'Acme', 'USD', '2026-07-01T00:00:00+00:00', 1)"
    )
    conn.commit()

    snapshot_path = run_pipeline.snapshot_warehouse(conn, "2026-07-17T05:15:23.456789+00:00")

    conn.execute(
        "INSERT INTO dim_account (account_id, platform, account_name, currency, valid_from, is_current) "
        "VALUES ('a2', 'meta_ads', 'Beta', 'USD', '2026-07-02T00:00:00+00:00', 1)"
    )
    conn.commit()

    snapshot_conn = sqlite3.connect(snapshot_path)
    count = snapshot_conn.execute("SELECT COUNT(*) FROM dim_account").fetchone()[0]
    snapshot_conn.close()
    assert count == 1


def test_snapshot_warehouse_prunes_beyond_snapshots_to_keep(isolated_paths, monkeypatch):
    monkeypatch.setattr(run_pipeline, "SNAPSHOTS_TO_KEEP", 2)
    conn = run_pipeline.init_warehouse()

    timestamps = [
        "2026-07-17T05:00:00.000000+00:00",
        "2026-07-17T05:01:00.000000+00:00",
        "2026-07-17T05:02:00.000000+00:00",
    ]
    for as_of in timestamps:
        run_pipeline.snapshot_warehouse(conn, as_of)

    remaining = sorted(p.name for p in run_pipeline.SNAPSHOT_DIR.glob("pipeline_*.db"))
    assert len(remaining) == 2
    assert "05-00-00" not in "".join(remaining)  # the oldest snapshot was pruned


def test_export_dashboard_data_includes_data_quality_summary(isolated_paths):
    conn = run_pipeline.init_warehouse()
    data_quality = {"rejected_ratios": {"google_ads": 0.03}, "drift_fields": {}}

    run_pipeline.export_dashboard_data(conn, reconciliation_results=[], data_quality=data_quality)

    summary = json.loads((isolated_paths / "dashboard_data" / "pipeline_run_summary.json").read_text())
    assert summary["data_quality"] == data_quality
