"""Runs the entire pipeline end-to-end without AWS: generate seed bronze data -> Glue
validation (bronze -> silver/rejected, the real `glue_jobs/bronze_to_silver.py`,
invoked exactly as `statemachine/ads_ingestion.asl.json`'s GlueTransform state would) ->
load silver into a local SQLite warehouse using the same SCD2/merge logic as
`redshift/*.sql` -> export the final tables to JSON for the React dashboard.

Nothing here is a shortcut around the real pipeline logic: bronze_to_silver.py runs as
its actual CLI subprocess against real bronze files; the SQL below mirrors each
redshift/*.sql file's business logic statement-for-statement (cross-referenced in each
function's docstring), translated to SQLite only because there is no live Redshift
Serverless workgroup for `lambda_handlers/reconciliation_check.py` to call. See that
handler's own docstring for why this script -- not that Lambda -- runs reconciliation
here.

The 14-day window is deliberately loaded in TWO passes (days 1-7, then days 8-14), each
its own simulated scheduled run, because campaign metadata (Google Ads / Meta Ads both)
reflects whatever is current *at pull time* -- a mid-window campaign rename baked into
`seed_data/campaign_catalog.py` only produces a genuine `dim_campaign` SCD2 history
entry if it is loaded as two separate runs, not one.

CLI: python -m local_runner.run_pipeline [--days 14] [--reset]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from common.logging_config import enable_file_logging, get_logger
from seed_data.generate_seed_data import generate as generate_seed_data

logger = get_logger(__name__)

REJECTED_RATIO_ALERT_THRESHOLD = 0.10

REPO_ROOT = Path(__file__).resolve().parent.parent
LAKE_ROOT = REPO_ROOT / "data_lake"
WAREHOUSE_DB_PATH = REPO_ROOT / "warehouse" / "pipeline.db"
SCHEMA_PATH = Path(__file__).parent / "sqlite_schema.sql"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
SNAPSHOT_DIR = REPO_ROOT / "warehouse" / "snapshots"
SNAPSHOTS_TO_KEEP = 5
LOG_DIR = REPO_ROOT / "logs"

PARTITION_PATTERN = re.compile(
    r"^(?P<zone>bronze|silver|rejected)/platform=(?P<platform>[^/]+)/account_id=(?P<account_id>[^/]+)/"
    r"year=(?P<year>\d{4})/month=(?P<month>\d{2})/day=(?P<day>\d{2})/(?P<filename>[^/]+)$"
)


def reset_local_state() -> None:
    shutil.rmtree(LAKE_ROOT, ignore_errors=True)
    WAREHOUSE_DB_PATH.unlink(missing_ok=True)
    logger.info("reset local data lake and warehouse")


def run_glue_transform(start_date: date, end_date: date) -> dict:
    """Invoke the real Glue job script as a subprocess -- the same CLI contract
    `statemachine/ads_ingestion.asl.json`'s GlueTransform state (`glue:startJobRun.sync`)
    would supply as job arguments. Its stdout is one structured JSON log line per
    `common.logging_config` record; this parses the rejected-ratio and schema-drift
    metrics back out of that stream so `main()` can alert on them, rather than
    re-deriving validation results by re-reading silver/rejected itself."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "glue_jobs" / "bronze_to_silver.py"),
            "--bucket", str(LAKE_ROOT),
            "--start-date", start_date.isoformat(),
            "--until-date", end_date.isoformat(),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    rejected_ratios: dict[str, float] = {}
    drift_fields: dict[str, int] = {}
    for line in result.stdout.splitlines():
        print(f"  [glue] {line}")
        try:
            record = json.loads(line)
        except ValueError:
            continue
        # _JsonFormatter merges `extra={"fields": {...}}` straight into the top-level
        # payload (see common/logging_config.py) -- these keys are not nested.
        if record.get("metric") == "RejectedRatio":
            rejected_ratios[record["platform"]] = record["value"]
        elif record.get("metric") == "NewFieldCount":
            drift_fields[f"{record['platform']}.{record['field']}"] = record["count"]

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("bronze_to_silver.py failed")

    return {"rejected_ratios": rejected_ratios, "drift_fields": drift_fields}


def _list_silver_records(start_date: date, end_date: date) -> list[dict]:
    """Read every silver/ record in [start_date, end_date] -- the in-process equivalent
    of `redshift/copy_into_staging.sql`'s `COPY ... FROM 's3://.../silver/...'`."""
    silver_root = LAKE_ROOT / "silver"
    if not silver_root.exists():
        return []
    records = []
    for path in sorted(silver_root.rglob("*.json")):
        key = str(path.relative_to(LAKE_ROOT))
        match = PARTITION_PATTERN.match(key)
        if not match:
            continue
        record_date = date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
        if not (start_date <= record_date <= end_date):
            continue
        for line in path.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def init_warehouse() -> sqlite3.Connection:
    WAREHOUSE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(WAREHOUSE_DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    return conn


def snapshot_warehouse(conn: sqlite3.Connection, as_of: str) -> Path:
    """Point-in-time copy of the SQLite stand-in warehouse, taken before a load pass
    mutates it -- the local equivalent of a Redshift snapshot
    (`aws redshift create-cluster-snapshot`), which a real deployment would rely on for
    this instead of a file-level copy. Uses sqlite3's own backup API rather than a raw
    file copy so a concurrently-open connection can never yield a torn snapshot."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    # Keep microsecond precision in the filename -- the two load passes in one `main()`
    # run can land within the same wall-clock second, and truncating to seconds would
    # make the second pass's snapshot silently overwrite the first's.
    snapshot_name = f"pipeline_{as_of.replace('+00:00', 'Z').replace(':', '-').replace('.', '-')}.db"
    snapshot_path = SNAPSHOT_DIR / snapshot_name
    snapshot_conn = sqlite3.connect(snapshot_path)
    with snapshot_conn:
        conn.backup(snapshot_conn)
    snapshot_conn.close()

    existing_snapshots = sorted(SNAPSHOT_DIR.glob("pipeline_*.db"))
    for stale_snapshot in existing_snapshots[:-SNAPSHOTS_TO_KEEP]:
        stale_snapshot.unlink()

    logger.info("wrote warehouse snapshot", extra={"fields": {"path": str(snapshot_path)}})
    return snapshot_path


def copy_into_staging(conn: sqlite3.Connection, records: list[dict]) -> None:
    """Mirrors redshift/copy_into_staging.sql: truncate + reload staging from the
    complete silver/ zone for this pass's date range, then derive the account/campaign
    staging tables and backfill dim_date -- all in one transaction, same as the real SQL
    file runs as one batchExecuteStatement."""
    conn.execute("DELETE FROM staging_campaign_performance")
    conn.executemany(
        """INSERT INTO staging_campaign_performance
           (platform, account_id, account_name, currency, campaign_id, campaign_name,
            channel_type, report_date, impressions, clicks, cost, conversions, conversions_value)
           VALUES (:platform, :account_id, :account_name, :currency, :campaign_id, :campaign_name,
                   :channel_type, :date, :impressions, :clicks, :cost, :conversions, :conversions_value)""",
        [{**r, "channel_type": r.get("channel_type")} for r in records],
    )

    conn.execute("DELETE FROM staging_account")
    conn.execute(
        """INSERT INTO staging_account (account_id, platform, account_name, currency)
           SELECT DISTINCT account_id, platform, account_name, currency FROM staging_campaign_performance"""
    )

    conn.execute("DELETE FROM staging_campaign")
    conn.execute(
        """INSERT INTO staging_campaign (campaign_id, account_id, platform, campaign_name, channel_type)
           SELECT DISTINCT campaign_id, account_id, platform, campaign_name, channel_type
           FROM staging_campaign_performance"""
    )

    for row in conn.execute("SELECT DISTINCT report_date FROM staging_campaign_performance"):
        report_date = date.fromisoformat(row[0])
        conn.execute(
            """INSERT OR IGNORE INTO dim_date (date_key, year, month, day, day_of_week, is_weekend)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                report_date.isoformat(),
                report_date.year,
                report_date.month,
                report_date.day,
                report_date.weekday(),
                1 if report_date.weekday() >= 5 else 0,
            ),
        )
    conn.commit()


def scd2_dim_account(conn: sqlite3.Connection, as_of: str) -> None:
    """Mirrors redshift/scd2_dim_account_close.sql + scd2_dim_account_insert.sql."""
    conn.execute(
        """UPDATE dim_account SET valid_to = ?, is_current = 0
           WHERE is_current = 1 AND (account_id, platform) IN (
               SELECT d.account_id, d.platform FROM dim_account d
               JOIN staging_account s ON s.account_id = d.account_id AND s.platform = d.platform
               WHERE d.is_current = 1
                 AND (d.account_name IS NOT s.account_name OR d.currency IS NOT s.currency)
           )""",
        (as_of,),
    )
    conn.execute(
        """INSERT INTO dim_account (account_id, platform, account_name, currency, valid_from, valid_to, is_current)
           SELECT DISTINCT s.account_id, s.platform, s.account_name, s.currency, ?, NULL, 1
           FROM staging_account s
           LEFT JOIN dim_account d
             ON d.account_id = s.account_id AND d.platform = s.platform AND d.is_current = 1
           WHERE d.dim_account_key IS NULL""",
        (as_of,),
    )
    conn.commit()


def scd2_dim_campaign(conn: sqlite3.Connection, as_of: str) -> None:
    """Mirrors redshift/scd2_dim_campaign_close.sql + scd2_dim_campaign_insert.sql."""
    conn.execute(
        """UPDATE dim_campaign SET valid_to = ?, is_current = 0
           WHERE is_current = 1 AND (campaign_id, platform) IN (
               SELECT d.campaign_id, d.platform FROM dim_campaign d
               JOIN staging_campaign s ON s.campaign_id = d.campaign_id AND s.platform = d.platform
               WHERE d.is_current = 1
                 AND (d.campaign_name IS NOT s.campaign_name OR d.channel_type IS NOT s.channel_type)
           )""",
        (as_of,),
    )
    conn.execute(
        """INSERT INTO dim_campaign
               (campaign_id, account_id, platform, campaign_name, channel_type, valid_from, valid_to, is_current)
           SELECT DISTINCT s.campaign_id, s.account_id, s.platform, s.campaign_name, s.channel_type, ?, NULL, 1
           FROM staging_campaign s
           LEFT JOIN dim_campaign d
             ON d.campaign_id = s.campaign_id AND d.platform = s.platform AND d.is_current = 1
           WHERE d.dim_campaign_key IS NULL""",
        (as_of,),
    )
    conn.commit()


def scd2_fct_campaign_performance_history(conn: sqlite3.Connection, as_of: str) -> None:
    """Mirrors redshift/scd2_fct_campaign_performance_close.sql + _insert.sql."""
    conn.execute(
        """UPDATE fct_campaign_performance_history SET valid_to = ?, is_current = 0
           WHERE is_current = 1 AND rowid IN (
               SELECT h.rowid FROM fct_campaign_performance_history h
               JOIN staging_campaign_performance s
                 ON s.platform = h.platform AND s.account_id = h.account_id
                AND s.campaign_id = h.campaign_id AND s.report_date = h.report_date
               WHERE h.is_current = 1
                 AND (h.impressions IS NOT s.impressions OR h.clicks IS NOT s.clicks
                      OR h.cost IS NOT s.cost OR h.conversions IS NOT s.conversions
                      OR h.conversions_value IS NOT s.conversions_value)
           )""",
        (as_of,),
    )
    conn.execute(
        """INSERT INTO fct_campaign_performance_history
           (platform, account_id, campaign_id, report_date, impressions, clicks, cost,
            conversions, conversions_value, valid_from, valid_to, is_current)
           SELECT s.platform, s.account_id, s.campaign_id, s.report_date, s.impressions, s.clicks,
                  s.cost, s.conversions, s.conversions_value, ?, NULL, 1
           FROM staging_campaign_performance s
           LEFT JOIN fct_campaign_performance_history h
             ON h.platform = s.platform AND h.account_id = s.account_id
            AND h.campaign_id = s.campaign_id AND h.report_date = s.report_date AND h.is_current = 1
           WHERE h.platform IS NULL""",
        (as_of,),
    )
    conn.commit()


def merge_fct_campaign_performance(conn: sqlite3.Connection, as_of: str) -> None:
    """Mirrors redshift/merge_fct_campaign_performance.sql. Redshift has a native MERGE
    statement; SQLite doesn't, so INSERT ... ON CONFLICT DO UPDATE is the closest
    equivalent -- same unconditional-update-on-match semantics, since staging is fully
    reloaded every pass just like the real target."""
    conn.execute(
        """INSERT INTO fct_campaign_performance
              (platform, account_id, campaign_id, report_date, campaign_name,
               impressions, clicks, cost, conversions, conversions_value, updated_at)
            SELECT platform, account_id, campaign_id, report_date, campaign_name,
                   impressions, clicks, cost, conversions, conversions_value, ?
            FROM staging_campaign_performance
            WHERE campaign_name IS NOT NULL
            ON CONFLICT (platform, account_id, campaign_id, report_date) DO UPDATE SET
                campaign_name = excluded.campaign_name,
                impressions = excluded.impressions,
                clicks = excluded.clicks,
                cost = excluded.cost,
                conversions = excluded.conversions,
                conversions_value = excluded.conversions_value,
                updated_at = excluded.updated_at""",
        (as_of,),
    )
    conn.commit()


def reconciliation_check(conn: sqlite3.Connection, start_date: date, end_date: date) -> dict:
    """Mirrors redshift/reconciliation_check.sql, run in-process the same way
    `lambda_handlers/reconciliation_check.py` would via the Redshift Data API against a
    real workgroup -- see that handler's docstring for why this demo runs it here
    instead."""
    row = conn.execute(
        """SELECT
             (SELECT COUNT(*) FROM staging_campaign_performance WHERE report_date BETWEEN ? AND ?),
             (SELECT COUNT(*) FROM fct_campaign_performance WHERE report_date BETWEEN ? AND ?),
             (SELECT COALESCE(SUM(cost), 0) FROM staging_campaign_performance WHERE report_date BETWEEN ? AND ?),
             (SELECT COALESCE(SUM(cost), 0) FROM fct_campaign_performance WHERE report_date BETWEEN ? AND ?)""",
        (start_date.isoformat(), end_date.isoformat()) * 4,
    ).fetchone()
    staging_rows, fact_rows, staging_cost, fact_cost = row
    result = {
        "status": "OK" if staging_rows == fact_rows else "MISMATCH",
        "staging_rows": staging_rows,
        "fact_rows": fact_rows,
        "staging_cost": round(staging_cost, 2),
        "fact_cost": round(fact_cost, 2),
    }
    logger.info("reconciliation check complete", extra={"fields": result})
    return result


def run_redshift_load_pass(conn: sqlite3.Connection, start_date: date, end_date: date) -> dict:
    """One full pass of statemachine/redshift_load.asl.json's states, in order."""
    as_of = datetime.now(UTC).isoformat()
    records = _list_silver_records(start_date, end_date)
    copy_into_staging(conn, records)
    scd2_dim_account(conn, as_of)
    scd2_dim_campaign(conn, as_of)
    scd2_fct_campaign_performance_history(conn, as_of)
    merge_fct_campaign_performance(conn, as_of)
    return reconciliation_check(conn, start_date, end_date)


def _rejected_summary() -> dict:
    rejected_root = LAKE_ROOT / "rejected"
    counts_by_platform: dict[str, int] = {}
    reasons: dict[str, int] = {}
    samples: list[dict] = []
    if rejected_root.exists():
        for path in sorted(rejected_root.rglob("*.json")):
            match = PARTITION_PATTERN.match(str(path.relative_to(LAKE_ROOT)))
            platform = match.group("platform") if match else "unknown"
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                counts_by_platform[platform] = counts_by_platform.get(platform, 0) + 1
                reason = record.get("_validation_error", "unknown")
                reasons[reason] = reasons.get(reason, 0) + 1
                if len(samples) < 20:
                    samples.append(record)
    return {"counts_by_platform": counts_by_platform, "reasons": reasons, "samples": samples}


def export_dashboard_data(
    conn: sqlite3.Connection, reconciliation_results: list[dict], data_quality: dict
) -> None:
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn.row_factory = sqlite3.Row

    accounts = [dict(r) for r in conn.execute(
        "SELECT account_id, platform, account_name, currency FROM dim_account WHERE is_current = 1"
    )]
    campaigns = [dict(r) for r in conn.execute(
        "SELECT campaign_id, account_id, platform, campaign_name, channel_type FROM dim_campaign WHERE is_current = 1"
    )]
    campaign_history = [dict(r) for r in conn.execute(
        """SELECT campaign_id, platform, campaign_name, channel_type, valid_from, valid_to, is_current
           FROM dim_campaign ORDER BY campaign_id, valid_from"""
    )]
    performance = [dict(r) for r in conn.execute(
        """SELECT f.platform, f.account_id, a.account_name, f.campaign_id, f.campaign_name,
                  c.channel_type, f.report_date, f.impressions, f.clicks, f.cost, f.conversions, f.conversions_value
           FROM fct_campaign_performance f
           JOIN dim_account a ON a.account_id = f.account_id AND a.platform = f.platform AND a.is_current = 1
           LEFT JOIN dim_campaign c ON c.campaign_id = f.campaign_id AND c.platform = f.platform AND c.is_current = 1
           ORDER BY f.report_date, f.platform, f.account_id"""
    )]

    (DASHBOARD_DATA_DIR / "accounts.json").write_text(json.dumps(accounts, indent=2))
    (DASHBOARD_DATA_DIR / "campaigns.json").write_text(json.dumps(campaigns, indent=2))
    (DASHBOARD_DATA_DIR / "campaign_history.json").write_text(json.dumps(campaign_history, indent=2))
    (DASHBOARD_DATA_DIR / "campaign_performance.json").write_text(json.dumps(performance, indent=2))
    (DASHBOARD_DATA_DIR / "rejected_summary.json").write_text(json.dumps(_rejected_summary(), indent=2))
    (DASHBOARD_DATA_DIR / "pipeline_run_summary.json").write_text(json.dumps(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "reconciliation_passes": reconciliation_results,
            "data_quality": data_quality,
        },
        indent=2,
    ))
    logger.info("exported dashboard data", extra={"fields": {"rows": len(performance)}})


def main() -> None:
    # Loaded here, not at module import time, so importing this module (as the test
    # suite does) never depends on -- or mutates the process environment with -- a
    # repo-root .env file. common.notifications reads TEAMS_WEBHOOK_URL at ITS import
    # time, so the .env has to be in place before that import runs, which is why it's
    # deferred to here too rather than sitting at the top of this file.
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    from common.notifications import send_teams_alert

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    log_path = enable_file_logging(LOG_DIR / f"pipeline_run_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.jsonl")
    print(f"Logging to stdout and {log_path}")

    if args.reset:
        reset_local_state()

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=args.days - 1)
    mid_date = start_date + timedelta(days=(args.days // 2) - 1)
    rename_cutover = mid_date + timedelta(days=1)

    print(f"Generating seed data for {start_date} .. {end_date} (rename cutover {rename_cutover})")
    generate_seed_data(start_date, end_date, rename_cutover)

    print("Running Glue bronze -> silver/rejected validation")
    data_quality = run_glue_transform(start_date, end_date)
    for platform, ratio in data_quality["rejected_ratios"].items():
        if ratio > REJECTED_RATIO_ALERT_THRESHOLD:
            send_teams_alert(
                "Data quality threshold breached",
                f"{platform} rejected {ratio:.1%} of records in {start_date} .. {end_date}, "
                f"above the {REJECTED_RATIO_ALERT_THRESHOLD:.0%} alert threshold.",
                facts={"platform": platform, "rejected_ratio": f"{ratio:.1%}"},
            )

    print("Initializing local warehouse (SQLite stand-in for Redshift)")
    conn = init_warehouse()

    reconciliation_results = []
    for pass_start, pass_end in [(start_date, mid_date), (rename_cutover, end_date)]:
        snapshot_warehouse(conn, datetime.now(UTC).isoformat())
        print(f"Running redshift_load pass for {pass_start} .. {pass_end}")
        result = run_redshift_load_pass(conn, pass_start, pass_end)
        if result["status"] == "MISMATCH":
            send_teams_alert(
                "Reconciliation mismatch",
                f"Staging vs. fact row/cost mismatch for {pass_start} .. {pass_end}.",
                facts=result,
            )
        reconciliation_results.append(
            {"start_date": pass_start.isoformat(), "end_date": pass_end.isoformat(), **result}
        )

    print("Exporting dashboard data")
    export_dashboard_data(conn, reconciliation_results, data_quality)
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
