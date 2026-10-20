import subprocess
from pathlib import Path

import pytest

from hpc_gantt import UploadError, upload

DEST = "dropbox:/QuakeCoRE/hpc_usage_gantt.png"


def test_upload_runs_rclone_copyto():
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    upload(Path("/tmp/chart.png"), DEST, run=run)
    assert calls == [(["rclone", "copyto", "/tmp/chart.png", DEST], {"capture_output": True, "text": True, "timeout": 300})]


def test_missing_rclone_is_explained():
    def run(args, **kwargs):
        raise FileNotFoundError("rclone")

    with pytest.raises(UploadError, match="rclone isn't installed"):
        upload(Path("/tmp/chart.png"), DEST, run=run)


def test_rclone_failure_shows_its_last_error_line():
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "2026/10/20 NOTICE: x\n2026/10/20 ERROR : token expired\n\n")

    with pytest.raises(UploadError, match="rclone failed: 2026/10/20 ERROR : token expired$"):
        upload(Path("/tmp/chart.png"), DEST, run=run)


def test_rclone_timeout_is_explained():
    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 300)

    with pytest.raises(UploadError, match="timed out"):
        upload(Path("/tmp/chart.png"), DEST, run=run)
