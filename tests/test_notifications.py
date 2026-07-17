import common.notifications as notifications


def test_demo_mode_is_on_by_default():
    # DEMO_MODE still exists here for parity with common/secrets.py, but no longer
    # gates send_teams_alert -- only TEAMS_WEBHOOK_URL does (see module docstring).
    assert notifications.DEMO_MODE is True


def test_send_teams_alert_logs_instead_of_posting_without_a_webhook(monkeypatch):
    monkeypatch.setattr(notifications, "TEAMS_WEBHOOK_URL", "")
    warnings = []
    monkeypatch.setattr(notifications.logger, "warning", lambda msg, **kwargs: warnings.append((msg, kwargs)))

    sent = notifications.send_teams_alert("Test title", "Test body", facts={"platform": "google_ads"})

    assert sent is False
    assert len(warnings) == 1
    message, kwargs = warnings[0]
    assert message == "teams alert not sent (no TEAMS_WEBHOOK_URL configured)"
    assert kwargs["extra"]["fields"]["title"] == "Test title"
    assert kwargs["extra"]["fields"]["platform"] == "google_ads"


def test_send_teams_alert_does_not_post_without_a_webhook_even_if_demo_mode_is_off(monkeypatch):
    monkeypatch.setattr(notifications, "DEMO_MODE", False)
    monkeypatch.setattr(notifications, "TEAMS_WEBHOOK_URL", "")

    posted = []
    monkeypatch.setattr(notifications.requests, "post", lambda *a, **kw: posted.append((a, kw)))

    sent = notifications.send_teams_alert("Test title", "Test body")

    assert sent is False
    assert posted == []


def test_send_teams_alert_posts_when_demo_mode_off_and_webhook_configured(monkeypatch):
    monkeypatch.setattr(notifications, "DEMO_MODE", False)
    monkeypatch.setattr(notifications, "TEAMS_WEBHOOK_URL", "https://example.invalid/webhook")

    posted = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, json, timeout):
        posted["url"] = url
        posted["json"] = json
        posted["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(notifications.requests, "post", fake_post)

    sent = notifications.send_teams_alert(
        "Reconciliation mismatch", "Staging vs. fact mismatch", facts={"status": "MISMATCH"}
    )

    assert sent is True
    assert posted["url"] == "https://example.invalid/webhook"
    assert posted["json"]["title"] == "Reconciliation mismatch"
    assert posted["json"]["sections"][0]["facts"] == [{"name": "status", "value": "MISMATCH"}]


def test_send_teams_alert_returns_false_and_logs_on_a_broken_webhook(monkeypatch):
    # A misconfigured or unreachable webhook (e.g. a placeholder URL) must never crash
    # the pipeline run over a missed notification.
    monkeypatch.setattr(notifications, "DEMO_MODE", False)
    monkeypatch.setattr(notifications, "TEAMS_WEBHOOK_URL", "https://placeholder.invalid/webhook")

    def broken_post(*a, **kw):
        raise notifications.requests.ConnectionError("name resolution failed")

    monkeypatch.setattr(notifications.requests, "post", broken_post)

    errors = []
    monkeypatch.setattr(notifications.logger, "error", lambda msg, **kwargs: errors.append((msg, kwargs)))

    sent = notifications.send_teams_alert("Test title", "Test body")

    assert sent is False
    assert len(errors) == 1
    message, kwargs = errors[0]
    assert message == "teams alert failed to send"
    assert kwargs["extra"]["fields"]["title"] == "Test title"
    assert "name resolution failed" in kwargs["extra"]["fields"]["error"]
