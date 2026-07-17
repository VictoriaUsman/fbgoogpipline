from datetime import date

import pytest

import connectors.base as base_module
from common.secrets import Credentials
from connectors.base import PlatformApiError, RetryableSession
from connectors.google_ads_connector import GoogleAdsConnector
from connectors.meta_ads_connector import MetaAdsConnector, ReportStatus


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise base_module.requests.HTTPError(f"status {self.status_code}")


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    # Every test in this file simulates transient failures; retry backoff must never
    # actually block the test suite for real (would-be seconds of jittered sleep).
    monkeypatch.setattr(base_module.time, "sleep", lambda *_args, **_kwargs: None)


def test_retryable_session_returns_first_success_immediately(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    session = RetryableSession()
    response = session.request("GET", "https://example.test/x")
    assert response.json() == {"ok": True}
    assert len(calls) == 1


def test_retryable_session_retries_on_retryable_status_then_succeeds(monkeypatch):
    responses = [FakeResponse(503), FakeResponse(429), FakeResponse(200, {"ok": True})]

    def fake_request(method, url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    session = RetryableSession(max_attempts=5)
    response = session.request("GET", "https://example.test/x")
    assert response.json() == {"ok": True}
    assert responses == []


def test_retryable_session_raises_platform_error_on_status_exhaustion(monkeypatch):
    # On the final attempt, a still-retryable status calls response.raise_for_status()
    # directly rather than falling through to PlatformApiError -- see connectors/base.py.
    def fake_request(method, url, **kwargs):
        return FakeResponse(500)

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    session = RetryableSession(max_attempts=3)
    with pytest.raises(base_module.requests.HTTPError, match="status 500"):
        session.request("GET", "https://example.test/x")


def test_retryable_session_raises_platform_error_on_connection_error_exhaustion(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise base_module.requests.ConnectionError("boom")

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    session = RetryableSession(max_attempts=3)
    with pytest.raises(PlatformApiError, match="exhausted 3 attempts"):
        session.request("GET", "https://example.test/x")


def test_retryable_session_does_not_retry_non_retryable_status(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(1)
        return FakeResponse(404)

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    session = RetryableSession(max_attempts=5)
    response = session.request("GET", "https://example.test/x")
    assert response.status_code == 404
    assert len(calls) == 1


GOOGLE_CREDENTIALS = Credentials(
    access_token="demo-token::google", developer_token="demo-developer-token", login_customer_id="999-888-7777"
)


def test_google_ads_connector_flattens_and_paginates(monkeypatch):
    pages = [
        {
            "results": [
                {
                    "segments": {"date": "2026-07-03"},
                    "campaign": {"id": 7001001, "name": "Search - Brand", "advertisingChannelType": "SEARCH"},
                    "metrics": {
                        "impressions": "1000",
                        "clicks": "50",
                        "costMicros": "123450000",
                        "conversions": 4.0,
                        "conversionsValue": 200.0,
                    },
                }
            ],
            "nextPageToken": "page-2",
        },
        {
            "results": [
                {
                    "segments": {"date": "2026-07-04"},
                    "campaign": {"id": 7001001, "name": "Search - Brand", "advertisingChannelType": "SEARCH"},
                    "metrics": {"impressions": 500, "clicks": 20, "costMicros": 0, "conversions": 1.0},
                }
            ]
        },
    ]

    captured_bodies = []

    def fake_request(method, url, **kwargs):
        import json as json_module

        captured_bodies.append(json_module.loads(kwargs["data"]))
        return FakeResponse(200, pages.pop(0))

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    connector = GoogleAdsConnector(customer_id="111-222-3333", credentials=GOOGLE_CREDENTIALS)
    rows = list(connector.query_campaign_performance(date(2026, 7, 3), date(2026, 7, 4)))

    assert len(rows) == 2
    assert rows[0] == {
        "date": "2026-07-03",
        "campaign_id": "7001001",
        "campaign_name": "Search - Brand",
        "channel_type": "SEARCH",
        "impressions": 1000,
        "clicks": 50,
        "cost": 123.45,
        "conversions": 4.0,
        "conversions_value": 200.0,
    }
    assert rows[1]["conversions_value"] == 0.0
    # Second request must carry the pageToken from the first page's response.
    assert "pageToken" not in captured_bodies[0]
    assert captured_bodies[1]["pageToken"] == "page-2"


def test_google_ads_connector_customer_id_strips_dashes():
    connector = GoogleAdsConnector(customer_id="111-222-3333", credentials=GOOGLE_CREDENTIALS)
    assert connector._customer_id == "1112223333"


def test_google_ads_connector_headers_include_developer_token_and_login_customer_id():
    connector = GoogleAdsConnector(customer_id="111-222-3333", credentials=GOOGLE_CREDENTIALS)
    headers = connector._headers()
    assert headers["Authorization"] == "Bearer demo-token::google"
    assert headers["developer-token"] == "demo-developer-token"
    assert headers["login-customer-id"] == "9998887777"


def test_google_ads_connector_headers_omit_optional_fields_when_absent():
    bare_credentials = Credentials(access_token="demo-token::bare")
    connector = GoogleAdsConnector(customer_id="111-222-3333", credentials=bare_credentials)
    headers = connector._headers()
    assert "developer-token" not in headers
    assert "login-customer-id" not in headers


META_CREDENTIALS = Credentials(access_token="demo-token::meta")


def test_meta_ads_connector_create_report_returns_run_id(monkeypatch):
    def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/insights")
        assert kwargs["params"]["time_increment"] == 1
        return FakeResponse(200, {"report_run_id": "run-123"})

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    connector = MetaAdsConnector(ad_account_id="act_10150123456789", credentials=META_CREDENTIALS)
    assert connector.create_report(date(2026, 7, 3), date(2026, 7, 9)) == "run-123"


def test_meta_ads_connector_poll_report_maps_status(monkeypatch):
    def fake_request(method, url, **kwargs):
        return FakeResponse(200, {"async_status": "Job Completed", "async_percent_completion": 100})

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    connector = MetaAdsConnector(ad_account_id="act_10150123456789", credentials=META_CREDENTIALS)
    status = connector.poll_report("run-123")
    assert status == ReportStatus(status="Job Completed", percent_complete=100)


def test_meta_ads_connector_download_report_paginates_and_flattens(monkeypatch):
    pages = [
        {
            "data": [
                {
                    "date_start": "2026-07-03",
                    "campaign_id": "23860222000001",
                    "campaign_name": "Lead Gen - Decision Makers",
                    "impressions": "2000",
                    "clicks": "80",
                    "spend": "55.5",
                    "actions": [
                        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "2"},
                        {"action_type": "link_click", "value": "80"},
                    ],
                    "action_values": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "100.0"}],
                }
            ],
            "paging": {"next": "https://graph.facebook.com/v19.0/run-123/insights?after=cursor2"},
        },
        {"data": []},
    ]

    def fake_request(method, url, **kwargs):
        return FakeResponse(200, pages.pop(0))

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    connector = MetaAdsConnector(ad_account_id="act_10150123456789", credentials=META_CREDENTIALS)
    rows = list(connector.download_report("run-123"))

    assert len(rows) == 1
    assert rows[0] == {
        "date": "2026-07-03",
        "campaign_id": "23860222000001",
        "campaign_name": "Lead Gen - Decision Makers",
        "impressions": 2000,
        "clicks": 80,
        "cost": 55.5,
        "conversions": 2.0,
        "conversions_value": 100.0,
    }


def test_meta_ads_connector_download_report_handles_no_matching_actions(monkeypatch):
    def fake_request(method, url, **kwargs):
        return FakeResponse(
            200,
            {
                "data": [
                    {
                        "date_start": "2026-07-03",
                        "campaign_id": "1",
                        "campaign_name": "No conversions",
                        "impressions": 10,
                        "clicks": 1,
                        "spend": "1.0",
                        "actions": [{"action_type": "link_click", "value": "1"}],
                    }
                ]
            },
        )

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    connector = MetaAdsConnector(ad_account_id="act_10150123456789", credentials=META_CREDENTIALS)
    rows = list(connector.download_report("run-1"))
    assert rows[0]["conversions"] == 0.0
    assert rows[0]["conversions_value"] == 0.0


def test_meta_ads_connector_logs_warning_above_usage_threshold(monkeypatch):
    # get_logger() caches a module-singleton logger with propagate=False, so neither
    # caplog (hooks the root logger) nor capsys (its handler's stdout reference predates
    # the fixture) observe these records -- spy on the module's logger.warning directly.
    import connectors.meta_ads_connector as meta_module

    warnings = []
    monkeypatch.setattr(meta_module.logger, "warning", lambda msg, **kwargs: warnings.append((msg, kwargs)))

    def fake_request(method, url, **kwargs):
        headers = {"X-Business-Use-Case-Usage": '{"act_123": [{"call_count": 95}]}'}
        return FakeResponse(200, {"report_run_id": "run-1"}, headers=headers)

    monkeypatch.setattr(base_module.requests, "request", fake_request)
    connector = MetaAdsConnector(ad_account_id="act_10150123456789", credentials=META_CREDENTIALS)
    connector.create_report(date(2026, 7, 3), date(2026, 7, 9))

    assert len(warnings) == 1
    message, kwargs = warnings[0]
    assert message == "approaching Meta rate limit"
    assert kwargs["extra"]["fields"]["usage_pct"] == 95
