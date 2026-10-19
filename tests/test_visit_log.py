"""Visit log: device labels, password gate, and which events are stored."""

import os
import tempfile

import pytz
from flask import Flask

from visit_log import VisitLog, accepted_event, device_label, passwords_match, register_visit_routes


def _log(directory: str) -> VisitLog:
    return VisitLog(
        path=os.path.join(directory, "visits.log"),
        timezone=pytz.timezone("America/New_York"),
        max_lines=3,
    )


def _client(log: VisitLog, password: str = "secret"):
    app = Flask(__name__)
    register_visit_routes(app, log, lambda: password)
    return app.test_client()


def test_device_label_is_short() -> None:
    assert device_label("") == "Unknown"
    assert device_label("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)") == "iPhone"
    assert device_label("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)") == "iPad"
    assert device_label("Mozilla/5.0 (Linux; Android 14)") == "Android"
    assert device_label("Mozilla/5.0 (Windows NT 10.0)") == "Desktop"


def test_only_page_opens_and_tab_clicks_are_kept() -> None:
    assert accepted_event("open", "dashboard") == ("open", "dashboard")
    assert accepted_event("tab", "Live Projections") == ("tab", "Live Projections")
    assert accepted_event("tab", "Current Standings") == ("tab", "Current Standings")
    assert accepted_event("open", "<script>") is None
    assert accepted_event("click", "dashboard") is None


def test_password_must_match() -> None:
    assert passwords_match("secret", "secret") is True
    assert passwords_match("secret", "Secret") is False
    assert passwords_match("", "secret") is False
    assert passwords_match("secret", "") is False


def test_log_page_is_hidden_without_a_password() -> None:
    with tempfile.TemporaryDirectory() as directory:
        client = _client(_log(directory), password="")
        response = client.get("/log")
        assert response.status_code == 404


def test_log_page_requires_the_password() -> None:
    with tempfile.TemporaryDirectory() as directory:
        log = _log(directory)
        client = _client(log)
        denied = client.get("/log")
        assert denied.status_code == 401
        wrong = client.get("/log", auth=("eli", "nope"))
        assert wrong.status_code == 401
        opened = client.get("/log", auth=("anyone", "secret"))
        assert opened.status_code == 200
        assert b"No visits recorded yet." in opened.data


def test_beacon_stores_a_tab_click_and_ignores_junk() -> None:
    with tempfile.TemporaryDirectory() as directory:
        log = _log(directory)
        client = _client(log)
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
        posted = client.post(
            "/visit",
            data={"event": "tab", "detail": "Live Projections"},
            headers={"User-Agent": ua},
        )
        assert posted.status_code == 204
        junk = client.post("/visit", data={"event": "open", "detail": "nope"})
        assert junk.status_code == 204
        lines = log.lines()
        assert len(lines) == 1
        assert "tab" in lines[0]
        assert "Live Projections" in lines[0]
        assert "iPhone" in lines[0]
        page = client.get("/log", auth=("eli", "secret"))
        assert b"Live Projections" in page.data
        assert b"iPhone" in page.data


def test_log_keeps_only_the_newest_lines() -> None:
    with tempfile.TemporaryDirectory() as directory:
        log = _log(directory)
        for detail in ("Current Standings", "Live Projections", "Current Standings", "Live Projections"):
            log.record("tab", detail, "Mozilla/5.0")
        lines = log.lines()
        assert len(lines) == 3
        assert lines[0].endswith("| Desktop")
