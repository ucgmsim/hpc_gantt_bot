import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import hpc_reminder
from helpers import EXAMPLE_TABS, EXPECTED_HEADS_UP, EXPECTED_REPLY, EXPECTED_WEEKLY, LINK, make_xlsx
from hpc_reminder import (Config, ConfigError, SheetError, SlackError, format_sheet_error, load_config,
                          run_heads_up, run_weekly, state_path)

TS = "1700000000.000100"


@pytest.fixture
def world(monkeypatch, tmp_path):
    posts = []
    monkeypatch.setattr(hpc_reminder, "download_workbook", lambda sheet_id: make_xlsx(EXAMPLE_TABS))

    def fake_post(token, channel, text, thread_ts=None):
        posts.append((text, thread_ts))
        return TS

    monkeypatch.setattr(hpc_reminder, "post_message", fake_post)
    return SimpleNamespace(posts=posts, state=tmp_path / "state.json", config=Config("SHEET_ID", "xoxb-test", "C123"))


def test_weekly_posts_plan_then_problem_thread(world):
    # a Wednesday catch-up run still covers the week of Monday 19 Oct
    assert run_weekly(date(2026, 10, 21), world.config, world.state) == 0
    assert world.posts == [(EXPECTED_WEEKLY, None), (EXPECTED_REPLY, TS)]
    assert json.loads(world.state.read_text()) == {"weekly": "2026-10-19"}


def test_weekly_posts_once_per_week_unless_forced(world):
    run_weekly(date(2026, 10, 19), world.config, world.state)
    assert run_weekly(date(2026, 10, 19), world.config, world.state) == 0 and len(world.posts) == 2
    run_weekly(date(2026, 10, 19), world.config, world.state, force=True)
    assert len(world.posts) == 4


def test_dry_run_prints_without_slack_or_state(world, capsys):
    assert run_weekly(date(2026, 10, 19), Config("SHEET_ID"), world.state, dry_run=True) == 0
    out = capsys.readouterr().out
    assert EXPECTED_WEEKLY in out and "--- thread reply ---\n" + EXPECTED_REPLY in out
    assert world.posts == [] and not world.state.exists()


def test_heads_up_on_friday(world):
    assert run_heads_up(date(2026, 10, 23), world.config, world.state) == 0
    assert world.posts == [(EXPECTED_HEADS_UP, None)]
    assert json.loads(world.state.read_text()) == {"heads-up": "2026-10-26"}


def test_heads_up_catch_up_on_monday_is_skipped(world):
    assert run_heads_up(date(2026, 10, 26), world.config, world.state, force=True) == 0
    assert world.posts == []


def test_heads_up_with_nothing_starting_posts_nothing(world):
    assert run_heads_up(date(2026, 10, 30), world.config, world.state) == 0
    assert world.posts == []


def test_unreadable_sheet_is_reported_in_the_channel(world, monkeypatch):
    def broken(sheet_id):
        raise SheetError("download failed with HTTP 404")

    monkeypatch.setattr(hpc_reminder, "download_workbook", broken)
    assert run_weekly(date(2026, 10, 19), world.config, world.state) == 1
    assert world.posts == [(format_sheet_error("the Monday plan", "download failed with HTTP 404", LINK), None)]
    assert not world.state.exists()


def test_slack_failure_exits_1_and_records_nothing(world, monkeypatch):
    def failing(token, channel, text, thread_ts=None):
        raise SlackError("Slack said: channel_not_found")

    monkeypatch.setattr(hpc_reminder, "post_message", failing)
    assert run_weekly(date(2026, 10, 19), world.config, world.state) == 1
    assert not world.state.exists()


def test_load_config():
    assert load_config({"SHEET_ID": "abc"}, need_slack=False) == Config("abc")
    with pytest.raises(ConfigError, match="SLACK_BOT_TOKEN, SLACK_CHANNEL"):
        load_config({"SHEET_ID": "abc", "SLACK_CHANNEL": ""}, need_slack=True)
    with pytest.raises(ConfigError, match="SHEET_ID"):
        load_config({}, need_slack=False)


def test_state_path():
    assert state_path({"STATE_DIRECTORY": "/var/lib/hpc-reminder"}) == Path("/var/lib/hpc-reminder/state.json")
    assert state_path({}) == Path.home() / ".local/state/hpc-reminder/state.json"


def test_cli_flags_reach_the_command(monkeypatch, tmp_path):
    seen = {}

    def fake_run(today, config, state, dry_run=False, force=False):
        seen.update(today=today, config=config, state=state, dry_run=dry_run, force=force)
        return 0

    monkeypatch.setattr(hpc_reminder, "run_weekly", fake_run)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_CHANNEL", raising=False)
    monkeypatch.setenv("SHEET_ID", "abc")
    monkeypatch.setenv("STATE_DIRECTORY", str(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        hpc_reminder.app(["weekly", "--dry-run", "--pretend-today-is", "2026-10-21"])
    assert exit_info.value.code == 0
    assert seen == {"today": date(2026, 10, 21), "config": Config("abc"), "state": tmp_path / "state.json",
                    "dry_run": True, "force": False}
