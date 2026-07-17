import json
from datetime import date

import pytest

import common.s3_paths as s3_paths
from common.bronze_writer import write_bronze_ndjson


@pytest.fixture(autouse=True)
def isolated_lake_root(tmp_path, monkeypatch):
    monkeypatch.setattr(s3_paths, "LAKE_ROOT", tmp_path)
    return tmp_path


def test_write_bronze_ndjson_partitions_by_each_rows_own_date(isolated_lake_root):
    rows = [
        {"date": "2026-07-03", "campaign_id": "1", "cost": 1.0},
        {"date": "2026-07-04", "campaign_id": "1", "cost": 2.0},
        {"date": "2026-07-03", "campaign_id": "2", "cost": 3.0},
    ]
    total = write_bronze_ndjson(rows, platform="google_ads", account_id="111-222-3333")
    assert total == 3

    jul3_key = s3_paths.object_key(
        "bronze", platform="google_ads", account_id="111-222-3333", report_date=date(2026, 7, 3)
    )
    jul4_key = s3_paths.object_key(
        "bronze", platform="google_ads", account_id="111-222-3333", report_date=date(2026, 7, 4)
    )
    jul3_rows = [json.loads(line) for line in (isolated_lake_root / jul3_key).read_text().splitlines()]
    jul4_rows = [json.loads(line) for line in (isolated_lake_root / jul4_key).read_text().splitlines()]

    assert len(jul3_rows) == 2
    assert len(jul4_rows) == 1


def test_write_bronze_ndjson_empty_input_writes_nothing(isolated_lake_root):
    total = write_bronze_ndjson([], platform="meta_ads", account_id="act_1")
    assert total == 0
    assert list(isolated_lake_root.glob("**/*.json")) == []


def test_write_bronze_ndjson_flushes_in_row_threshold_batches(isolated_lake_root, monkeypatch):
    import common.bronze_writer as bronze_writer_module

    monkeypatch.setattr(bronze_writer_module, "FLUSH_ROW_THRESHOLD", 2)
    rows = [{"date": "2026-07-03", "campaign_id": str(i)} for i in range(5)]
    total = write_bronze_ndjson(rows, platform="google_ads", account_id="111-222-3333")
    assert total == 5

    part_files = sorted(
        (isolated_lake_root / "bronze" / "platform=google_ads" / "account_id=111-222-3333").glob(
            "year=2026/month=07/day=03/*.json"
        )
    )
    # 5 rows at a threshold of 2 -> flushes of 2, 2, then a final flush of 1 = 3 parts.
    assert len(part_files) == 3
