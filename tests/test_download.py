import pytest
import requests

import hpc_gantt
from hpc_gantt import SheetError, download_workbook

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class FakeResponse:
    """The parts of a requests.Response that download_workbook reads."""

    def __init__(self, status_code: int = 200, headers: dict[str, str] | None = None, content: bytes = b""):
        self.status_code, self.headers, self.content = status_code, headers or {}, content


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hpc_gantt.time, "sleep", lambda seconds: None)


def fake_get(monkeypatch: pytest.MonkeyPatch, *outcomes):
    """Make requests.get return or raise the given outcomes in turn; return the list of URLs requested."""
    urls, queue = [], list(outcomes)

    def get(url: str, **kwargs):
        urls.append(url)
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(hpc_gantt.requests, "get", get)
    return urls


def test_download_returns_the_workbook(monkeypatch: pytest.MonkeyPatch):
    urls = fake_get(monkeypatch, FakeResponse(200, {"Content-Type": XLSX}, b"PK"))
    assert download_workbook("abc") == b"PK"
    assert urls == ["https://docs.google.com/spreadsheets/d/abc/export?format=xlsx"]


def test_sign_in_page_points_at_sharing(monkeypatch: pytest.MonkeyPatch):
    fake_get(monkeypatch, FakeResponse(200, {"Content-Type": "text/html; charset=utf-8"}, b"<html>"))
    with pytest.raises(SheetError, match="Anyone with the link can view"):
        download_workbook("abc")


def test_http_error_is_not_retried(monkeypatch: pytest.MonkeyPatch):
    urls = fake_get(monkeypatch, FakeResponse(404))
    with pytest.raises(SheetError, match="HTTP 404"):
        download_workbook("abc")
    assert len(urls) == 1


def test_server_errors_are_retried(monkeypatch: pytest.MonkeyPatch):
    urls = fake_get(monkeypatch, FakeResponse(503), FakeResponse(503), FakeResponse(200, {"Content-Type": XLSX}, b"PK"))
    assert download_workbook("abc") == b"PK" and len(urls) == 3


def test_network_failure_gives_up_after_three_tries(monkeypatch: pytest.MonkeyPatch):
    urls = fake_get(monkeypatch, *[requests.ConnectionError("down")] * 3)
    with pytest.raises(SheetError, match="download failed"):
        download_workbook("abc")
    assert len(urls) == 3
