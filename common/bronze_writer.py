"""Streaming writer shared by `report_requester` (Google Ads' synchronous path writes
directly here) and `report_downloader` (Meta Ads' async path writes here after a report
completes).

Rows are split by their own `date` field -- not the wall-clock time of the write -- so
each day lands under its own partition regardless of which day in the lookback window
it came from (see `common/s3_paths.object_key`). Flushing every `FLUSH_ROW_THRESHOLD`
rows bounds memory regardless of report size; at this pipeline's actual volume (a
handful of accounts, ~14 days) it never triggers mid-stream, but the discipline is kept
because unbounded Lambda memory growth is exactly how the analogous step in the Amazon
Ads reference pipeline broke in practice at 26-profile scale.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from common.logging_config import get_logger
from common.s3_paths import local_path, object_key
from common.versioning import write_versioned

logger = get_logger(__name__)

FLUSH_ROW_THRESHOLD = 50_000


def write_bronze_ndjson(rows: Iterable[dict], *, platform: str, account_id: str) -> int:
    """Stream `rows` into bronze/, partitioned by each row's own `date`. Returns row count written."""
    buffers: dict[date, list[dict]] = defaultdict(list)
    parts: dict[date, int] = defaultdict(int)
    total_written = 0

    def flush(report_date: date) -> None:
        nonlocal total_written
        buffer = buffers[report_date]
        if not buffer:
            return
        key = object_key(
            "bronze", platform=platform, account_id=account_id, report_date=report_date, part=parts[report_date]
        )
        path = local_path(key)
        content = "".join(json.dumps(row) + "\n" for row in buffer)
        write_versioned(path, content)
        total_written += len(buffer)
        parts[report_date] += 1
        buffer.clear()

    last_known_date = date.today()
    for row in rows:
        try:
            report_date = date.fromisoformat(row["date"])
            last_known_date = report_date
        except (TypeError, ValueError):
            # A row with a genuinely malformed date (e.g. seed_data's "bad_date"
            # corruption mode) still belongs in bronze -- validate_record() is the
            # intended rejection point, not this writer. File it under the nearest
            # known-good partition so it still falls inside the requested window.
            logger.warning(
                "row has an unparseable date -- writing to bronze under the nearest "
                "known-good partition; Glue validation will reject it downstream",
                extra={"fields": {"platform": platform, "account_id": account_id, "raw_date": row.get("date")}},
            )
            report_date = last_known_date
        buffers[report_date].append(row)
        if len(buffers[report_date]) >= FLUSH_ROW_THRESHOLD:
            flush(report_date)

    for report_date in list(buffers):
        flush(report_date)

    logger.info(
        "wrote bronze rows",
        extra={"fields": {"platform": platform, "account_id": account_id, "rows_written": total_written}},
    )
    return total_written
