# Google Ads & Meta Ads Pipeline

A demo ad-reporting data pipeline for Google Ads and Meta Ads, architected the same
way as the [Amazon Ads Pipeline](../AD%20Platform%20Pipeline) this project is modeled
on: connectors → Step Functions-orchestrated Lambdas → an S3 medallion lake →
Glue-based validation → a Redshift SCD2 warehouse. A static React dashboard reads the
warehouse's output directly (no backend server) to visualize the result.

**Nothing here is deployed to AWS.** This is a local, runnable stand-in for the real
architecture — see [Scope](#scope-vs-the-amazon-ads-reference-pipeline) below for
exactly what was cut and why.

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

python -m local_runner.run_pipeline --reset --days 14
```

This regenerates seed data, runs Glue-style validation, and loads the SQLite stand-in
warehouse across two simulated daily load passes, then writes the dashboard's JSON
data files. Expect output like:

```
seed: wrote 168 bronze rows across 4 accounts
glue: 163 valid / 5 rejected
reconciliation 2026-07-03..2026-07-09: OK (83 staging rows == 83 fact rows, $27,287.76 == $27,287.76)
reconciliation 2026-07-10..2026-07-16: OK (80 staging rows == 80 fact rows, $25,876.83 == $25,876.83)
```

Then run the dashboard:

```bash
cd dashboard
npm install
npm run dev       # http://localhost:5173, reads dashboard/public/data/*.json
```

Run the test suite and lint:

```bash
pytest tests/ -v
ruff check .
```

## Architecture

```
config/accounts.yaml (2 Google Ads + 2 Meta Ads accounts)
        │
        ▼
EventBridge (daily) ──▶ Step Functions: ads_ingestion.asl.json
        │
        ▼
  PrepareMapInput (Lambda)
        │  builds one {platform, account} item per configured account
        ▼
  Map state, MaxConcurrency=8 ── one pipeline, platform as a fan-out dimension
   ┌─────────────────────────────────────────────────────────┐
   │ RequestReport (Lambda)                                  │
   │   google_ads → GAQL search, rows in hand synchronously  │
   │   meta_ads   → POST /insights?async=true, report_run_id │
   │        │                                                │
   │        ▼ IsAsyncPlatform (Choice)                       │
   │   google_ads: skip straight to bronze/                  │
   │   meta_ads:   WaitBeforePoll(30s) → PollReportStatus     │
   │               → loop until COMPLETED/FAILED/30 polls    │
   │        │                                                │
   │        ▼                                                │
   │   DownloadReport (Lambda, meta_ads only) → bronze/       │
   └─────────────────────────────────────────────────────────┘
        │
        ▼
  GlueTransform: glue_jobs/bronze_to_silver.py
        │  validation/rules.py — hard gate on required fields / types / ISO dates
        │  valid → silver/, invalid → rejected/ (with _validation_error), schema
        │  drift on unrecognized fields is logged as a signal, never a rejection
        ▼
Step Functions: redshift_load.asl.json
        │  COPY silver/ → staging, then SCD2 dimension close+insert and fact merge
        ▼
  dim_account, dim_campaign (SCD2)  +  fct_campaign_performance (current-state,
  MERGE upsert)  +  fct_campaign_performance_history (full periodic-snapshot log)
        │
        ▼
local_runner/run_pipeline.py exports dashboard/public/data/*.json
        │
        ▼
React dashboard (static, no server) — spend/conversions trends, platform
breakdown, campaign table, SCD2 history viewer, rejected-records panel,
reconciliation status
```

### Why Google Ads and Meta Ads don't share one fetch interface

Google Ads' API (`connectors/google_ads_connector.py`) is a synchronous, paginated
GAQL query — rows come back in the same request/response cycle. Meta Ads'
(`connectors/meta_ads_connector.py`) is a genuine async report job: create → poll →
download, exactly like the Amazon Ads reference pipeline's connector. Forcing both
into one abstract base class would mean one of them implements no-op stubs for
methods that don't apply. Instead, both only share
`connectors/base.py`'s `RetryableSession` — retry/backoff on 429/5xx is genuinely
identical across platforms; the fetch shape is not. The state machine's
`IsAsyncPlatform` Choice state (keyed on `RequestReport`'s `status` field) is what
lets a single Map iterator handle both shapes side by side.

### SCD2 in SQLite

`local_runner/run_pipeline.py` is a local stand-in for Redshift Serverless — nothing
here is actually deployed. It re-implements the same SCD2 semantics the `redshift/*.sql`
scripts define (`dim_account`, `dim_campaign` close+insert; `fct_campaign_performance`
MERGE upsert; `fct_campaign_performance_history` full snapshot log), translated to
SQLite: `IS DISTINCT FROM` → `IS NOT`, `MERGE` → `INSERT ... ON CONFLICT DO UPDATE`,
`IDENTITY(1,1)` → `INTEGER PRIMARY KEY AUTOINCREMENT`.

To prove the SCD2 history is genuine rather than hand-faked, the 14-day demo window
is loaded in **two separate simulated daily runs** (Jul 3–9, then Jul 10–16), split at
a mid-window campaign rename. `dim_campaign`'s version chain for the renamed
campaigns only has two rows because two real load passes ran — not because a fixture
says so. `dashboard/public/data/campaign_history.json` shows the result.

## Scope vs. the Amazon Ads reference pipeline

This project intentionally cuts everything the reference pipeline has beyond the core
ingest → validate → warehouse path, to keep it demo-sized:

- **Core pipeline only** — no SAM/CloudFormation, no CloudWatch alarms or paging, no
  disaster-recovery scripts. The `Comment` fields in the ASL JSON describe what a real
  deployment would add (e.g. `BranchFailureCount` metrics), but nothing here actually
  provisions AWS resources.
- **One pipeline, platform as a fan-out dimension** — a single Map state over
  `{platform, account}` items, rather than one state machine per ad platform.
- **A smaller demo dataset** — 2 Google Ads accounts + 2 Meta Ads accounts, 14 days,
  ~168 seed rows total, instead of the reference pipeline's larger account/day volume.
- **DEMO_MODE=1** (default, see `common/secrets.py`) — real Google/Meta OAuth is out of
  scope; credential resolution returns a fixed stub token and the real refresh-token /
  system-user-token functions raise `NotImplementedError` deliberately.
- **SQLite instead of Redshift Serverless** — see above. `local_runner/run_pipeline.py`
  runs the pipeline end-to-end on a laptop with no AWS account.

## Repository layout

| Path | What it is |
|---|---|
| `connectors/` | `base.py` (shared retry/backoff), `google_ads_connector.py`, `meta_ads_connector.py` |
| `lambda_handlers/` | `prepare_map_input.py`, `report_requester.py`, `report_poller.py`, `report_downloader.py` |
| `common/` | `secrets.py`, `scheduling.py`, `s3_paths.py`, `bronze_writer.py`, `logging_config.py` |
| `validation/rules.py` | `validate_record()` (hard gate) and `detect_new_fields()` (drift signal) |
| `glue_jobs/bronze_to_silver.py` | Bronze → silver/rejected split, run as a standalone CLI script |
| `statemachine/` | `ads_ingestion.asl.json`, `redshift_load.asl.json` |
| `redshift/` | SCD2 dimension + fact SQL, written for real Redshift syntax |
| `seed_data/` | `generate_seed_data.py`, `campaign_catalog.py` — realistic, seeded-random demo data with a ~3% invalid rate and a ~5% drift rate |
| `local_runner/run_pipeline.py` | Local orchestrator: seed → Glue validation subprocess → SQLite SCD2 load → dashboard JSON export |
| `dashboard/` | Static React (Vite) dashboard reading `dashboard/public/data/*.json` |
| `tests/` | pytest suite — validation rules, scheduling, connectors, bronze writer, S3 paths, Glue job, lambda integration |
| `.github/workflows/ci.yml` | ruff lint, ASL JSON validation, pytest |

## Dashboard

Hand-rolled SVG charts (no charting library) so mark specs, hover/tooltip behavior,
and the categorical palette are fully controlled and validated for colorblind-safe
contrast rather than eyeballed. Panels: daily spend and conversions trends (kept as
two separate one-axis charts, never dual-axis), spend-by-platform breakdown, a
sortable campaign table, the `dim_campaign` SCD2 version-chain viewer, a
rejected-records panel grouped by normalized rejection reason, and per-load-pass
reconciliation status. Supports light/dark mode and per-platform filtering.

```bash
cd dashboard && npm install && npm run dev
```
