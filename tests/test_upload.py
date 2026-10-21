import subprocess
from pathlib import Path

import pytest

from hpc_gantt import DESTINATION, UploadError, rclone_upload


def test_upload_runs_rclone_copyto():
    calls = []

    def run(args: list[str], **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    rclone_upload(Path("/tmp/chart.png"), DESTINATION, run=run)
    assert calls == [
        (
            ["rclone", "copyto", "/tmp/chart.png", DESTINATION],
            {"capture_output": True, "text": True, "timeout": 300},
        )
    ]


def test_missing_rclone_is_explained():
    def run(args: list[str], **kwargs):
        raise FileNotFoundError("rclone")

    with pytest.raises(UploadError, match="rclone isn't installed"):
        rclone_upload(Path("/tmp/chart.png"), DESTINATION, run=run)


def test_rclone_failure_shows_its_last_error_line():
    def run(args: list[str], **kwargs):
        return subprocess.CompletedProcess(
            args, 1, "", "2026/10/20 NOTICE: x\n2026/10/20 ERROR : token expired\n\n"
        )

    with pytest.raises(
        UploadError, match="rclone failed: 2026/10/20 ERROR : token expired$"
    ):
        rclone_upload(Path("/tmp/chart.png"), DESTINATION, run=run)


def test_rclone_timeout_is_explained():
    def run(args: list[str], **kwargs):
        raise subprocess.TimeoutExpired(args, 300)

    with pytest.raises(UploadError, match="timed out"):
        rclone_upload(Path("/tmp/chart.png"), DESTINATION, run=run)
