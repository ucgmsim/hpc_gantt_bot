from datetime import date

from helpers import EXPECTED_HEADS_UP, EXPECTED_REPLY, EXPECTED_WEEKLY, LINK
from hpc_reminder import (Hpc, Person, Run, Schedule, format_heads_up_post, format_problem_reply,
                          format_sheet_error, format_weekly_post, sheet_url)

MORGAN = Person("Morgan", "U06EFG6HIJ", True)


def test_weekly_post(example_schedule):
    assert format_weekly_post(example_schedule, date(2026, 10, 19), LINK) == EXPECTED_WEEKLY


def test_heads_up_post(example_schedule):
    assert format_heads_up_post(example_schedule, date(2026, 10, 26), LINK) == EXPECTED_HEADS_UP
    assert format_heads_up_post(example_schedule, date(2026, 11, 2), LINK) is None


def test_problem_reply(example_schedule):
    assert format_problem_reply(example_schedule) == EXPECTED_REPLY
    assert format_problem_reply(Schedule([MORGAN], [], [], [])) is None
    assert format_problem_reply(Schedule([MORGAN], [], [], ["a", "b"])).startswith("<@U06EFG6HIJ> 2 problems in the sheet need fixing:\n• a\n")


def test_quiet_week_without_admin():
    s = Schedule([], [Hpc("Mahuika", True)], [], ["No admin is ticked on the People tab."])
    assert format_weekly_post(s, date(2026, 10, 19), LINK) == (
        ":spiral_calendar_pad: *HPC plan for this week* · Mon 19 – Sun 25 Oct\n\n"
        "Nothing planned this week.\n\n"
        ":warning: Nothing is planned on:\n• *Mahuika* this week\n• *Mahuika* next week (26 Oct – 1 Nov)\n\n"
        f"Plans changed? <{LINK}|Update the sheet>")
    assert format_problem_reply(s) == "1 problem in the sheet needs fixing:\n• No admin is ticked on the People tab."


def test_run_without_description():
    s = Schedule([MORGAN], [Hpc("Mahuika", False)], [Run(2, MORGAN, "", "Mahuika", date(2026, 10, 19), date(2026, 10, 20))], [])
    post = format_weekly_post(s, date(2026, 10, 19), LINK)
    assert "\n*Mahuika*\n• <@U06EFG6HIJ> (19 – 20 Oct)\n" in post
    assert ":warning:" not in post   # nothing watched, so no idle section


def test_sheet_text_is_escaped():
    s = Schedule([MORGAN], [Hpc("A&B <test>", True)],
                 [Run(2, MORGAN, "M<8 & >7 runs", "A&B <test>", date(2026, 10, 19), date(2026, 10, 20))],
                 ["Row 9 (<b>, ?): no HPC given, so it was skipped."])
    post = format_weekly_post(s, date(2026, 10, 19), LINK)
    assert "*A&amp;B &lt;test&gt;*" in post and "— M&lt;8 &amp; &gt;7 runs (" in post
    assert "Row 9 (&lt;b&gt;, ?)" in format_problem_reply(s)


def test_sheet_error_and_url():
    assert sheet_url("SHEET_ID") == LINK
    assert format_sheet_error("the Monday plan", "download failed with HTTP 404", LINK) == (
        f":x: Couldn't read the HPC planning sheet, so the Monday plan didn't go out: download failed with HTTP 404\n<{LINK}|Open the sheet>")
