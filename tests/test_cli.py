from datetime import date

import pytest

import hpc_gantt
from helpers import EXAMPLE_TABS, NOW, make_xlsx, png_size
from hpc_gantt import DESTINATION, SheetError, UploadError, update_chart


@pytest.fixture
def uploads(monkeypatch):
    """Serve the example sheet, and record the destination of each upload (checking it was a PNG)."""
    sent = []
    monkeypatch.setattr(hpc_gantt, "download_workbook", lambda sheet_id: make_xlsx(EXAMPLE_TABS))

    def fake_upload(local, destination):
        png_size(local)
        sent.append(destination)

    monkeypatch.setattr(hpc_gantt, "rclone_upload", fake_upload)
    return sent


def test_no_upload_writes_the_chart(uploads, tmp_path):
    assert update_chart("ID", NOW.date(), NOW, None, tmp_path / "c.png") == 0
    assert png_size(tmp_path / "c.png")[0] == 1680 and uploads == []


def test_upload_sends_a_fresh_png(uploads):
    assert update_chart("ID", NOW.date(), NOW, "dropbox:/test/x.png", None) == 0
    assert uploads == ["dropbox:/test/x.png"]


def test_unreadable_sheet_uploads_nothing(uploads, monkeypatch, capsys):
    def broken(sheet_id):
        raise SheetError("download failed with HTTP 404")

    monkeypatch.setattr(hpc_gantt, "download_workbook", broken)
    assert update_chart("ID", NOW.date(), NOW, DESTINATION, None) == 1
    assert uploads == [] and "HTTP 404" in capsys.readouterr().err


def test_upload_failure_exits_1(uploads, monkeypatch, capsys):
    def failing(local, destination):
        raise UploadError("rclone isn't installed (or isn't on PATH)")

    monkeypatch.setattr(hpc_gantt, "rclone_upload", failing)
    assert update_chart("ID", NOW.date(), NOW, DESTINATION, None) == 1
    assert "rclone isn't installed" in capsys.readouterr().err


def test_sheet_problems_go_to_stderr(uploads, tmp_path, capsys):
    update_chart("ID", NOW.date(), NOW, None, tmp_path / "c.png")
    assert 'Sheet problem: Row 6 (Casey, Frontera): start date "early Nov" isn\'t a date' in capsys.readouterr().err


def test_cli_flags(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(hpc_gantt, "update_chart", lambda sheet_id, today, now, upload_to, output: seen.append((sheet_id, today, upload_to, output)) or 0)
    monkeypatch.setenv("SHEET_ID", "abc")
    with pytest.raises(SystemExit) as no_upload:
        hpc_gantt.app(["--no-upload", "--output", str(tmp_path / "c.png"), "--pretend-today-is", "2026-10-20"])
    with pytest.raises(SystemExit) as default:
        hpc_gantt.app([])
    assert (no_upload.value.code, default.value.code) == (0, 0)
    assert seen[0] == ("abc", date(2026, 10, 20), None, tmp_path / "c.png")
    assert seen[1][2:] == (DESTINATION, None)


def test_missing_sheet_id(monkeypatch):
    monkeypatch.delenv("SHEET_ID", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        hpc_gantt.app(["--no-upload"])
    assert exit_info.value.code == 1
