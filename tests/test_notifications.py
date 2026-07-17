import common.notifications as notifications


def test_demo_mode_is_on_by_default():
    # Mirrors common/secrets.py -- this project has no real Teams channel, so every
    # test in this suite depends on DEMO_MODE never performing a real HTTP POST.
    assert notifications.DEMO_MODE is True


def test_send_teams_alert_logs_instead_of_posting_in_demo_mode(monkeypatch):
    warnings = []
    monkeypatch.setattr(notifications.logger, "warning", lambda msg, **kwargs: warnings.append((msg, kwargs)))

    sent = notifications.send_teams_alert("Test title", "Test body", facts={"platform": "google_ads"})

    assert sent is False
    assert len(warnings) == 1
    message, kwargs = warnings[0]
    assert message == "teams alert not sent (DEMO_MODE or no TEAMS_WEBHOOK_URL configured)"
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
