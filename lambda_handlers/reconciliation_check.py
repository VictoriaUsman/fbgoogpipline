"""Final state of `statemachine/redshift_load.asl.json`, run after every load regardless
of outcome (not just on mismatch) -- publishes an OK/MISMATCH result so a human always
sees confirmation the load reconciled, not just silence on success.

Compares `staging_campaign_performance` row counts/sums against what actually landed in
`fct_campaign_performance` for the run's date range, via the Redshift Data API
(`redshift/reconciliation_check.sql`). In production this calls
`boto3.client("redshift-data")`; this repo has no live Redshift Serverless workgroup to
call, so `local_runner/run_pipeline.py` runs the equivalent comparison directly against
the local SQLite stand-in instead of invoking this handler -- this file documents and
implements the real AWS-facing contract for when a workgroup exists to point it at.

Input:  {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "workgroup_name": str, "database": str}
Output: {"status": "OK" | "MISMATCH", "staging_rows": int, "fact_rows": int, "staging_cost": float, "fact_cost": float}
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from common.logging_config import get_logger

logger = get_logger(__name__)

RECONCILIATION_SQL_PATH = Path(__file__).resolve().parent.parent / "redshift" / "reconciliation_check.sql"
POLL_INTERVAL_SECONDS = 2
MAX_POLL_ATTEMPTS = 30


def handler(event: dict, _context: Any = None) -> dict:
    import boto3  # imported lazily: only needed against a real Redshift Serverless workgroup

    client = boto3.client("redshift-data")
    sql = RECONCILIATION_SQL_PATH.read_text().format(start_date=event["start_date"], end_date=event["end_date"])

    execution = client.execute_statement(
        WorkgroupName=event["workgroup_name"],
        Database=event["database"],
        Sql=sql,
    )
    statement_id = execution["Id"]

    for _ in range(MAX_POLL_ATTEMPTS):
        description = client.describe_statement(Id=statement_id)
        if description["Status"] in ("FINISHED", "FAILED", "ABORTED"):
            break
        time.sleep(POLL_INTERVAL_SECONDS)
    else:
        raise TimeoutError(f"reconciliation query {statement_id} did not finish in time")

    if description["Status"] != "FINISHED":
        raise RuntimeError(f"reconciliation query failed: {description.get('Error')}")

    result = client.get_statement_result(Id=statement_id)
    row = {col["label"]: list(value.values())[0] for col, value in zip(result["ColumnMetadata"], result["Records"][0])}

    status = "OK" if row["staging_rows"] == row["fact_rows"] else "MISMATCH"
    logger.info("reconciliation check complete", extra={"fields": {"status": status, **row}})
    return {"status": status, **row}
