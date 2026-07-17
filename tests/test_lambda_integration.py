"""Integration tests for lambda_handlers/*.py.

Every test here monkeypatches the connector classes rather than hitting real Google
Ads / Meta Ads APIs -- DEMO_MODE=1 (the default, see common/secrets.py) never performs
real OAuth, and these handlers must never attempt a real network call in this project.
"""

import json
from datetime import date

import pytest

import common.s3_paths as s3_paths
import lambda_handlers.prepare_map_input as prepare_map_input
import lambda_handlers.report_downloader as report_downloader
import lambda_handlers.report_poller as report_poller
import lambda_handlers.report_requester as report_requester
from connectors.meta_ads_connector import ReportStatus


@pytest.fixture(autouse=True)
def isolated_lake_root(tmp_path, monkeypatch):
    # Every handler under test writes bronze/ via common.s3_paths.local_path(), which
    # reads the module-level LAKE_ROOT global -- redirect it so tests never touch the
    # real data_lake/ directory this project's local runner also writes to.
    monkeypatch.setattr(s3_paths, "LAKE_ROOT", tmp_path)
    return tmp_path


def _read_bronze_rows(lake_root, *, platform, account_id, report_date):
    key = s3_paths.object_key("bronze", platform=platform, account_id=account_id, report_date=report_date, part=0)
    path = lake_root / key
    return [json.loads(line) for line in path.read_text().splitlines()]


# ---- prepare_map_input ----------------------------------------------------


def test_prepare_map_input_builds_one_item_per_configured_account():
    event = {"time": "2026-07-17T06:00:00Z"}
    result = prepare_map_input.handler(event)
    assert len(result["items"]) == 4  # 2 google_ads + 2 meta_ads accounts in config/accounts.yaml

    google_item = next(i for i in result["items"] if i["platform"] == "google_ads")
    assert google_item["account_id"] == "111-222-3333"
    assert google_item["start_date"] == "2026-07-10"
    assert google_item["end_date"] == "2026-07-16"
    assert google_item["login_customer_id"] is not None


def test_prepare_map_input_meta_items_have_no_login_customer_id():
    event = {"time": "2026-07-17T06:00:00Z"}
    result = prepare_map_input.handler(event)
    meta_item = next(i for i in result["items"] if i["platform"] == "meta_ads")
    assert meta_item["login_customer_id"] is None


# ---- report_requester -------------------------------------------------------


class FakeGoogleAdsConnector:
    last_init_kwargs = None

    def __init__(self, *, customer_id, credentials):
        FakeGoogleAdsConnector.last_init_kwargs = {"customer_id": customer_id, "credentials": credentials}

    def query_campaign_performance(self, start_date, end_date):
        yield {
            "date": start_date.isoformat(),
            "campaign_id": "7001001",
            "campaign_name": "Search - Brand",
            "channel_type": "SEARCH",
            "impressions": 1000,
            "clicks": 50,
            "cost": 12.34,
            "conversions": 1.0,
            "conversions_value": 20.0,
        }


class FakeMetaAdsConnectorForRequester:
    def __init__(self, *, ad_account_id, credentials):
        self.ad_account_id = ad_account_id

    def create_report(self, start_date, end_date):
        return f"run::{self.ad_account_id}"


def test_report_requester_google_ads_completes_synchronously(monkeypatch, isolated_lake_root):
    monkeypatch.setattr(report_requester, "GoogleAdsConnector", FakeGoogleAdsConnector)
    event = {
        "platform": "google_ads",
        "account_id": "111-222-3333",
        "account_name": "Acme Retail",
        "currency": "USD",
        "secret_name": "demo/google-ads/acme-retail",
        "login_customer_id": "999-888-7777",
        "start_date": "2026-07-10",
        "end_date": "2026-07-16",
    }
    result = report_requester.handler(event)

    assert result == {
        "platform": "google_ads",
        "account_id": "111-222-3333",
        "status": "COMPLETED",
        "rows_written": 1,
    }
    rows = _read_bronze_rows(
        isolated_lake_root, platform="google_ads", account_id="111-222-3333", report_date=date(2026, 7, 10)
    )
    assert rows[0]["account_name"] == "Acme Retail"
    assert rows[0]["currency"] == "USD"
    assert rows[0]["platform"] == "google_ads"


def test_report_requester_attaches_google_ads_developer_headers(monkeypatch, isolated_lake_root):
    monkeypatch.setattr(report_requester, "GoogleAdsConnector", FakeGoogleAdsConnector)
    event = {
        "platform": "google_ads",
        "account_id": "444-555-6666",
        "account_name": "Acme B2B",
        "currency": "USD",
        "secret_name": "demo/google-ads/acme-b2b",
        "login_customer_id": "999-888-7777",
        "start_date": "2026-07-10",
        "end_date": "2026-07-16",
    }
    report_requester.handler(event)
    credentials = FakeGoogleAdsConnector.last_init_kwargs["credentials"]
    assert credentials.developer_token == "demo-developer-token"
    assert credentials.login_customer_id == "999-888-7777"


def test_report_requester_meta_ads_returns_in_progress(monkeypatch):
    monkeypatch.setattr(report_requester, "MetaAdsConnector", FakeMetaAdsConnectorForRequester)
    event = {
        "platform": "meta_ads",
        "account_id": "act_10150123456789",
        "account_name": "Acme Retail",
        "currency": "USD",
        "secret_name": "demo/meta-ads/acme-retail",
        "start_date": "2026-07-10",
        "end_date": "2026-07-16",
    }
    result = report_requester.handler(event)
    assert result == {
        "platform": "meta_ads",
        "account_id": "act_10150123456789",
        "account_name": "Acme Retail",
        "currency": "USD",
        "secret_name": "demo/meta-ads/acme-retail",
        "status": "IN_PROGRESS",
        "report_run_id": "run::act_10150123456789",
        "poll_count": 0,
    }


def test_report_requester_unknown_platform_raises():
    event = {
        "platform": "tiktok_ads",
        "account_id": "x",
        "secret_name": "demo/x",
        "start_date": "2026-07-10",
        "end_date": "2026-07-16",
    }
    with pytest.raises(ValueError, match="unknown platform"):
        report_requester.handler(event)


# ---- report_poller -----------------------------------------------------------


class FakeMetaAdsConnectorForPoller:
    def __init__(self, status, *, ad_account_id=None, credentials=None):
        self._status = status

    def poll_report(self, report_run_id):
        return self._status


@pytest.mark.parametrize(
    "raw_status,expected",
    [
        ("Job Completed", "COMPLETED"),
        ("Job Failed", "FAILED"),
        ("Job Skipped", "FAILED"),
        ("Job Running", "IN_PROGRESS"),
    ],
)
def test_report_poller_maps_status(monkeypatch, raw_status, expected):
    fake_status = ReportStatus(status=raw_status, percent_complete=50)
    monkeypatch.setattr(
        report_poller, "MetaAdsConnector", lambda **kwargs: FakeMetaAdsConnectorForPoller(fake_status)
    )
    event = {
        "platform": "meta_ads",
        "account_id": "act_10150123456789",
        "account_name": "Acme Retail",
        "currency": "USD",
        "secret_name": "demo/meta-ads/acme-retail",
        "report_run_id": "run-1",
        "poll_count": 2,
    }
    result = report_poller.handler(event)
    assert result["status"] == expected
    assert result["poll_count"] == 3
    assert result["report_run_id"] == "run-1"


# ---- report_downloader --------------------------------------------------------


class FakeMetaAdsConnectorForDownloader:
    def __init__(self, *, ad_account_id, credentials):
        pass

    def download_report(self, report_run_id):
        yield {
            "date": "2026-07-10",
            "campaign_id": "23860222000001",
            "campaign_name": "Lead Gen - Decision Makers",
            "impressions": 500,
            "clicks": 20,
            "cost": 5.5,
            "conversions": 1.0,
            "conversions_value": 15.0,
        }


def test_report_downloader_completes_and_writes_bronze(monkeypatch, isolated_lake_root):
    monkeypatch.setattr(report_downloader, "MetaAdsConnector", FakeMetaAdsConnectorForDownloader)
    event = {
        "platform": "meta_ads",
        "account_id": "act_10150123456789",
        "account_name": "Acme Retail",
        "currency": "USD",
        "secret_name": "demo/meta-ads/acme-retail",
        "report_run_id": "run-1",
    }
    result = report_downloader.handler(event)
    assert result == {
        "platform": "meta_ads",
        "account_id": "act_10150123456789",
        "status": "COMPLETED",
        "rows_written": 1,
    }

    rows = _read_bronze_rows(
        isolated_lake_root, platform="meta_ads", account_id="act_10150123456789", report_date=date(2026, 7, 10)
    )
    assert rows[0]["campaign_name"] == "Lead Gen - Decision Makers"
    assert rows[0]["account_name"] == "Acme Retail"
