import pytest
import requests

import hpc_reminder
from helpers import FakeResponse
from hpc_reminder import SheetError, SlackError, download_workbook, post_message

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(hpc_reminder.time, "sleep", lambda seconds: None)


def fake(monkeypatch, name, *outcomes):
    """Make requests.<name> return or raise the given outcomes in turn; return the list of calls."""
    calls, queue = [], list(outcomes)

    def call(url, **kwargs):
        calls.append((url, kwargs))
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(hpc_reminder.requests, name, call)
    return calls


def test_download_returns_the_workbook(monkeypatch):
    calls = fake(monkeypatch, "get", FakeResponse(200, {"Content-Type": XLSX}, b"PK"))
    assert download_workbook("abc") == b"PK"
    assert calls[0][0] == "https://docs.google.com/spreadsheets/d/abc/export?format=xlsx"


def test_sign_in_page_points_at_sharing(monkeypatch):
    fake(monkeypatch, "get", FakeResponse(200, {"Content-Type": "text/html; charset=utf-8"}, b"<html>"))
    with pytest.raises(SheetError, match="Anyone with the link can view"):
        download_workbook("abc")


def test_http_error_is_not_retried(monkeypatch):
    calls = fake(monkeypatch, "get", FakeResponse(404))
    with pytest.raises(SheetError, match="HTTP 404"):
        download_workbook("abc")
    assert len(calls) == 1


def test_server_errors_are_retried(monkeypatch):
    calls = fake(monkeypatch, "get", FakeResponse(503), FakeResponse(503), FakeResponse(200, {"Content-Type": XLSX}, b"PK"))
    assert download_workbook("abc") == b"PK" and len(calls) == 3


def test_network_failure_gives_up_after_three_tries(monkeypatch):
    calls = fake(monkeypatch, "get", *[requests.ConnectionError("down")] * 3)
    with pytest.raises(SheetError, match="download failed"):
        download_workbook("abc")
    assert len(calls) == 3


def test_post_message_request(monkeypatch):
    calls = fake(monkeypatch, "post", FakeResponse(200, json_data={"ok": True, "ts": "1.2"}))
    assert post_message("xoxb-t", "C1", "hi", thread_ts="0.1") == "1.2"
    url, kwargs = calls[0]
    assert url == "https://slack.com/api/chat.postMessage"
    assert kwargs["headers"]["Authorization"] == "Bearer xoxb-t"
    assert kwargs["json"] == {"channel": "C1", "text": "hi", "unfurl_links": False, "unfurl_media": False, "thread_ts": "0.1"}


def test_post_without_thread_has_no_thread_ts(monkeypatch):
    calls = fake(monkeypatch, "post", FakeResponse(200, json_data={"ok": True, "ts": "1.2"}))
    post_message("xoxb-t", "C1", "hi")
    assert "thread_ts" not in calls[0][1]["json"]


def test_slack_refusal_is_not_retried(monkeypatch):
    calls = fake(monkeypatch, "post", FakeResponse(200, json_data={"ok": False, "error": "channel_not_found"}))
    with pytest.raises(SlackError, match="channel_not_found"):
        post_message("xoxb-t", "C1", "hi")
    assert len(calls) == 1


def test_slack_server_error_is_retried(monkeypatch):
    calls = fake(monkeypatch, "post", FakeResponse(500), FakeResponse(200, json_data={"ok": True, "ts": "1.2"}))
    assert post_message("xoxb-t", "C1", "hi") == "1.2" and len(calls) == 2
