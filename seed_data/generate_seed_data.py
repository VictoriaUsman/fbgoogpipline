"""Fabricates realistic bronze/ NDJSON data for every account/campaign in
`config/accounts.yaml`, standing in for two weeks' worth of real `report_requester` /
`report_downloader` output without needing live Google Ads / Meta Ads credentials.

This deliberately bypasses `connectors/` entirely rather than mocking their HTTP calls --
the connectors are real, production-shaped client code (see their module docstrings);
this script's only job is to hand `common.bronze_writer.write_bronze_ndjson` the same
shape of rows those connectors would have produced, so every downstream stage
(`glue_jobs/bronze_to_silver.py`, the Redshift SCD2/merge SQL) runs against genuine
bronze input instead of hand-faked warehouse rows.

A `campaign_rename_cutover` date is baked in deliberately: rows before it use each
campaign's original name, rows on/after it use `CampaignSpec.renamed_to` where set. This
exists so `local_runner/run_pipeline.py`, when it loads the two halves of the window in
two separate passes (mirroring two real scheduled runs on two different days), produces
a genuine SCD2 history entry in `dim_campaign` -- not a fabricated one.

A small fraction of rows are deliberately corrupted (missing field / negative cost /
malformed date) to exercise the rejected/ path, and a small fraction carry an
undeclared extra field to exercise schema-drift detection -- both real behaviors of
`validation/rules.py`, not hardcoded dashboard numbers.

CLI: --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --rename-cutover <YYYY-MM-DD>
"""

from __future__ import annotations

import argparse
import hashlib
import random
from datetime import date, timedelta
from pathlib import Path

import yaml

from common.bronze_writer import write_bronze_ndjson
from common.logging_config import get_logger
from seed_data.campaign_catalog import CAMPAIGNS_BY_ACCOUNT, CampaignSpec

logger = get_logger(__name__)

ACCOUNTS_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "accounts.yaml"

INVALID_RATE = 0.03
DRIFT_RATE = 0.05


def _seeded_rng(*parts: str) -> random.Random:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _generate_campaign_day(
    spec: CampaignSpec, report_date: date, *, platform: str, account_id: str, account_name: str, currency: str,
    use_renamed: bool,
) -> dict:
    rng = _seeded_rng(account_id, spec.campaign_id, report_date.isoformat())

    weekend_mult = spec.weekend_multiplier if report_date.weekday() >= 5 else 1.0
    spike_mult = rng.uniform(1.4, 2.2) if rng.random() < 0.1 else 1.0

    impressions = round(spec.avg_daily_impressions * weekend_mult * spike_mult * rng.uniform(0.85, 1.15))
    clicks = round(impressions * spec.ctr * rng.uniform(0.9, 1.1))
    cost = round(clicks * spec.cpc * rng.uniform(0.9, 1.1), 2)
    conversions = round(clicks * spec.cvr * rng.uniform(0.8, 1.2), 2)
    conversions_value = round(conversions * spec.aov * rng.uniform(0.9, 1.1), 2)

    campaign_name = spec.renamed_to if (use_renamed and spec.renamed_to) else spec.name

    record = {
        "date": report_date.isoformat(),
        "platform": platform,
        "account_id": account_id,
        "account_name": account_name,
        "currency": currency,
        "campaign_id": spec.campaign_id,
        "campaign_name": campaign_name,
        "impressions": impressions,
        "clicks": clicks,
        "cost": cost,
        "conversions": conversions,
        "conversions_value": conversions_value,
    }
    if spec.channel_type:
        record["channel_type"] = spec.channel_type

    if rng.random() < DRIFT_RATE:
        record["audience_segment" if platform == "meta_ads" else "ad_group_count"] = (
            rng.choice(["lookalike_1pct", "retargeting_30d", "broad"]) if platform == "meta_ads" else rng.randint(1, 5)
        )

    if rng.random() < INVALID_RATE:
        record = _corrupt(record, rng)

    return record


def _corrupt(record: dict, rng: random.Random) -> dict:
    mode = rng.choice(["missing_name", "negative_cost", "bad_date"])
    record = dict(record)
    if mode == "missing_name":
        del record["campaign_name"]
    elif mode == "negative_cost":
        record["cost"] = -abs(record["cost"])
    elif mode == "bad_date":
        record["date"] = "not-a-date"
    return record


def generate(start_date: date, end_date: date, rename_cutover: date) -> None:
    accounts = yaml.safe_load(ACCOUNTS_CONFIG_PATH.read_text())
    dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

    for account in accounts:
        specs = CAMPAIGNS_BY_ACCOUNT.get(account["account_id"], [])

        def rows_for_account(specs=specs, account=account):
            for spec in specs:
                for report_date in dates:
                    yield _generate_campaign_day(
                        spec,
                        report_date,
                        platform=account["platform"],
                        account_id=account["account_id"],
                        account_name=account["account_name"],
                        currency=account["currency"],
                        use_renamed=report_date >= rename_cutover,
                    )

        written = write_bronze_ndjson(
            rows_for_account(), platform=account["platform"], account_id=account["account_id"]
        )
        logger.info(
            "generated seed data for account",
            extra={"fields": {"account_id": account["account_id"], "rows_written": written}},
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--rename-cutover", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    generate(args.start_date, args.end_date, args.rename_cutover)


if __name__ == "__main__":
    main()
