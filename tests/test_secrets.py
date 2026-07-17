from common.secrets import DEMO_MODE, get_credentials


def test_demo_mode_is_on_by_default():
    # This whole project has nothing deployed and no real ad-account credentials --
    # every test in this suite depends on DEMO_MODE never performing real OAuth.
    assert DEMO_MODE is True


def test_get_credentials_returns_demo_stub_without_network_access():
    credentials = get_credentials("google_ads", "demo/google-ads/acme-retail")
    assert credentials.access_token == "demo-token::demo/google-ads/acme-retail"
    assert credentials.developer_token is None
    assert credentials.login_customer_id is None


def test_get_credentials_stub_is_platform_agnostic():
    google = get_credentials("google_ads", "same-secret-name")
    meta = get_credentials("meta_ads", "same-secret-name")
    assert google.access_token == meta.access_token == "demo-token::same-secret-name"


def test_get_credentials_is_cached_per_secret_name():
    first = get_credentials("meta_ads", "cache-probe-secret")
    second = get_credentials("meta_ads", "cache-probe-secret")
    assert first.access_token == second.access_token
