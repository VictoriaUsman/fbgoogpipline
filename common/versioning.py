"""Overwrite-preserving writes for every S3 zone (bronze/silver/rejected).

A real deployment would just turn on S3 bucket versioning
(`aws s3api put-bucket-versioning --bucket ... --versioning-configuration Status=Enabled`)
and let S3 keep every prior object body under the same key for free. There is no bucket
here, only a local directory tree, so `write_versioned` reproduces the same guarantee by
hand: before an object at `path` is overwritten, its current contents are copied into a
sibling `.versions/` directory first. Version files use a `.v<n>` suffix rather than
`.json` specifically so the directory walks in `glue_jobs/bronze_to_silver.py` and
`local_runner/run_pipeline.py` (which both glob for `*.json`) never mistake old versions
for new bronze/silver/rejected records.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def write_versioned(path: Path, content: str) -> None:
    """Write `content` to `path`, first archiving any existing object as the next version."""
    if path.exists():
        versions_dir = path.parent / ".versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        existing_versions = list(versions_dir.glob(f"{path.name}.v*"))
        next_version = len(existing_versions) + 1
        shutil.copy2(path, versions_dir / f"{path.name}.v{next_version}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
