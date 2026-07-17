"""AWS Glue Python Shell job (deliberately not Spark): validates every bronze/ record and
promotes it to silver/ or rejected/.

Python Shell rather than Spark because of volume -- a handful of accounts across two
platforms, daily aggregates for a rolling 7-day window, is at most a few thousand rows
per run. A Spark cluster's startup overhead would dwarf the actual processing time at
this scale; this is the same reasoning the Amazon Ads reference pipeline used at its
larger (26 profiles x 3 ad products) scale, and it holds even more clearly here.

Invoked by `statemachine/ads_ingestion.asl.json`'s `GlueTransform` state via the native
`glue:startJobRun.sync` integration -- no custom poll loop needed, unlike the Redshift
Data API steps in `redshift_load.asl.json`.

CLI: --bucket <data lake root> --start-date <YYYY-MM-DD> --until-date <YYYY-MM-DD>
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from common.logging_config import get_logger, log_fields
from common.s3_paths import swap_zone
from common.versioning import write_versioned
from validation.rules import detect_new_fields, validate_record

logger = get_logger(__name__)

BRONZE_KEY_PATTERN = re.compile(
    r"^bronze/platform=(?P<platform>[^/]+)/account_id=(?P<account_id>[^/]+)/"
    r"year=(?P<year>\d{4})/month=(?P<month>\d{2})/day=(?P<day>\d{2})/(?P<filename>[^/]+)$"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True, help="data lake root (local dir in this demo, S3 bucket in prod)")
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--until-date", required=True, type=date.fromisoformat)
    args = parser.parse_args()

    lake_root = Path(args.bucket)
    keys = _list_bronze_keys(lake_root, args.start_date, args.until_date)

    totals: Counter[str] = Counter()
    drift_fields: Counter[str] = Counter()

    for key in keys:
        match = BRONZE_KEY_PATTERN.match(key)
        platform = match.group("platform")
        valid_count, rejected_count, new_fields = _process_key(lake_root, key, platform)
        totals[f"{platform}.valid"] += valid_count
        totals[f"{platform}.rejected"] += rejected_count
        for field in new_fields:
            drift_fields[f"{platform}.{field}"] += 1

    for metric_key, count in totals.items():
        platform, outcome = metric_key.split(".")
        rejected = totals.get(f"{platform}.rejected", 0)
        valid = totals.get(f"{platform}.valid", 0)
        ratio = rejected / (valid + rejected) if (valid + rejected) else 0.0
        logger.info(
            "bronze_to_silver metrics",
            extra=log_fields(metric="RejectedRatio", platform=platform, ad_product=outcome, value=ratio),
        )

    for field_key, count in drift_fields.items():
        platform, field = field_key.split(".", 1)
        logger.warning(
            "schema drift detected",
            extra=log_fields(metric="NewFieldCount", platform=platform, field=field, count=count),
        )


def _list_bronze_keys(lake_root: Path, start_date: date, until_date: date) -> list[str]:
    """Paginate (in this demo: walk the local dir) under bronze/, filtered to the date window."""
    bronze_root = lake_root / "bronze"
    if not bronze_root.exists():
        return []
    keys = []
    for path in sorted(bronze_root.rglob("*.json")):
        key = str(path.relative_to(lake_root))
        match = BRONZE_KEY_PATTERN.match(key)
        if not match:
            continue
        record_date = date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
        if start_date <= record_date <= until_date:
            keys.append(key)
    return keys


def _process_key(lake_root: Path, key: str, platform: str) -> tuple[int, int, set[str]]:
    """Read one bronze NDJSON object, validate line-by-line, write to silver/ or rejected/."""
    valid_lines: list[str] = []
    rejected_lines: list[str] = []
    all_new_fields: set[str] = set()

    with (lake_root / key).open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            all_new_fields |= detect_new_fields(record, platform)

            reason = validate_record(record, platform)
            if reason is None:
                valid_lines.append(json.dumps(record))
            else:
                record["_validation_error"] = reason
                rejected_lines.append(json.dumps(record))

    if valid_lines:
        silver_path = lake_root / swap_zone(key, "silver")
        write_versioned(silver_path, "\n".join(valid_lines) + "\n")

    if rejected_lines:
        rejected_path = lake_root / swap_zone(key, "rejected")
        write_versioned(rejected_path, "\n".join(rejected_lines) + "\n")

    return len(valid_lines), len(rejected_lines), all_new_fields


if __name__ == "__main__":
    main()
