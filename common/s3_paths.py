"""The one sanctioned way to build or transform a data-lake object key.

In production this pipeline targets S3 (`bronze/`, `silver/`, `rejected/` zones under a
single bucket). Locally -- since nothing in this project is deployed, matching the
reference architecture's own status -- `LAKE_ROOT` points at a `data_lake/` directory on
disk with the identical Hive-style partitioning, so the same key layout that would be
used against `boto3.client("s3")` also works unmodified against `pathlib`/local files.

Never hand-build a key with string concatenation elsewhere in this codebase -- every
reader and writer, real or local, goes through `object_key()` / `swap_zone()`.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

LAKE_ROOT = Path(os.environ.get("LAKE_ROOT", "data_lake"))

ZONES = ("bronze", "silver", "rejected")


def object_key(
    zone: str,
    *,
    platform: str,
    account_id: str,
    report_date: date,
    part: int = 0,
) -> str:
    """Build a partitioned key: `<zone>/platform=<p>/account_id=<a>/year=/month=/day=/report_part<NNNN>.json`."""
    if zone not in ZONES:
        raise ValueError(f"unknown zone {zone!r}, expected one of {ZONES}")
    return (
        f"{zone}/platform={platform}/account_id={account_id}/"
        f"year={report_date.year:04d}/month={report_date.month:02d}/day={report_date.day:02d}/"
        f"report_part{part:04d}.json"
    )


def swap_zone(key: str, new_zone: str) -> str:
    """Rewrite the leading `<zone>/` segment of an existing key, keeping every partition segment intact."""
    if new_zone not in ZONES:
        raise ValueError(f"unknown zone {new_zone!r}, expected one of {ZONES}")
    _, _, rest = key.partition("/")
    return f"{new_zone}/{rest}"


def local_path(key: str) -> Path:
    """Resolve a logical object key to its on-disk path under LAKE_ROOT."""
    return LAKE_ROOT / key
