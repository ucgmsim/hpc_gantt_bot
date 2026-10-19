from datetime import date, datetime as D
from pathlib import Path

import pytest

from helpers import EXAMPLE_TABS, MON, make_xlsx, with_runs
from hpc_reminder import Hpc, Person, Run, SheetError, parse_schedule, read_workbook

d1, d2 = D(2026, 10, 19), D(2026, 10, 23)


def test_read_workbook_returns_rows_by_tab():
    xlsx = make_xlsx({"Runs": [["Person", "Start date"], ["Alex", D(2026, 10, 12)]], "People": [["Name", "Admin"], ["Alex", True]]})
    assert read_workbook(xlsx) == {
        "Runs": [("Person", "Start date"), ("Alex", D(2026, 10, 12))],
        "People": [("Name", "Admin"), ("Alex", True)],
    }


def test_read_workbook_rejects_a_sign_in_page():
    with pytest.raises(SheetError, match="couldn't open"):
        read_workbook(b"<html>Sign in</html>")


def test_parse_example(example_schedule):
    s = example_schedule
    assert [r.row for r in s.runs] == [2, 3, 4, 5]
    assert s.runs[0] == Run(2, Person("Alex", "U04ABC1DEF", False), "Hikurangi rupture scenarios", "Mahuika", date(2026, 10, 12), date(2026, 11, 1))
    assert [(h.name, h.watched) for h in s.hpcs] == [("Mahuika", True), ("Frontera", True), ("Setonix", True), ("Test cluster", False)]
    assert [p.name for p in s.admins] == ["Morgan"]
    assert s.problems == ['Row 6 (Casey, Frontera): start date "early Nov" isn\'t a date, so it was skipped.']


def test_names_match_ignoring_case_and_spaces():
    run = parse_schedule(with_runs([" alex ", None, "mahuika ", d1, d2]), MON).runs[0]
    assert (run.person.name, run.hpc, run.description) == ("Alex", "Mahuika", "")


def test_tabs_and_columns_are_found_by_name():
    tabs = {"runs": [["Person", "Description", "HPC", "Start date", "End date"]],
            "people": [["Admin", " slack member id ", "NAME"], [True, "U04ABC1DEF", "Alex"]],
            "HPCs": [["Alert if idle", "HPC"], [True, "Mahuika"]]}
    s = parse_schedule(tabs, MON)
    assert (s.people, s.hpcs, s.problems) == ([Person("Alex", "U04ABC1DEF", True)], [Hpc("Mahuika", True)], [])


def test_blank_rows_are_ignored():
    tabs = with_runs([None] * 5, ["  ", None, "", None, None])
    tabs["People"] = tabs["People"] + [[None, None, False]]
    tabs["HPCs"] = tabs["HPCs"] + [[None, False]]
    s = parse_schedule(tabs, MON)
    assert (s.runs, s.problems) == ([], [])


@pytest.mark.parametrize("row, problem", [
    (["Jamie", "x", "Mahuika", d1, d2], 'Row 2 (Jamie, Mahuika): "Jamie" isn\'t on the People tab with a valid Slack member ID, so it was skipped.'),
    (["Alex", "x", "Kupe", d1, d2], 'Row 2 (Alex, Kupe): HPC "Kupe" isn\'t on the HPCs tab, so it was skipped.'),
    ([None, "x", "Mahuika", d1, d2], "Row 2 (?, Mahuika): no person given, so it was skipped."),
    (["Alex", "x", "Mahuika", d2, d1], "Row 2 (Alex, Mahuika): start date is after the end date, so it was skipped."),
    (["Alex", "x", "Mahuika", d1, None], "Row 2 (Alex, Mahuika): end date is empty, so it was skipped."),
    (["Jamie", "x", "Kupe", d1, d2], 'Row 2 (Jamie, Kupe): "Jamie" isn\'t on the People tab with a valid Slack member ID; HPC "Kupe" isn\'t on the HPCs tab, so it was skipped.'),
])
def test_bad_rows_are_reported_and_skipped(row, problem):
    s = parse_schedule(with_runs(row), MON)
    assert (s.runs, s.problems) == ([], [problem])


def test_rows_that_ended_before_this_week_are_not_checked():
    s = parse_schedule(with_runs(["Jamie", "x", "Kupe", "early Oct", D(2026, 10, 18)]), MON)
    assert (s.runs, s.problems) == ([], [])


def test_unreadable_end_date_is_always_reported():
    s = parse_schedule(with_runs(["Alex", "x", "Mahuika", D(2026, 10, 1), "whenever"]), MON)
    assert s.problems == ['Row 2 (Alex, Mahuika): end date "whenever" isn\'t a date, so it was skipped.']


def test_sheet_level_problems():
    tabs = {
        "People": [["Name", "Slack member ID", "Admin"], ["Alex", "U04ABC1DEF", False], ["alex", "U09ZZZ9ZZZ", True], ["Sam", "sam", False]],
        "HPCs": [["HPC", "Alert if idle"], ["Mahuika", True], ["MAHUIKA", False]],
        "Runs": [["Person", "Description", "HPC", "Start date"]],
    }
    assert parse_schedule(tabs, MON).problems == [
        'The Runs tab has no "End date" column.',
        'People row 3: "alex" is already listed above, so this row was skipped.',
        'People row 4 (Sam): "sam" isn\'t a Slack member ID, so this row was skipped.',
        "No admin is ticked on the People tab.",
        'HPCs row 3: "MAHUIKA" is already listed above, so this row was skipped.',
    ]
    no_hpcs_tab = {"Runs": EXAMPLE_TABS["Runs"], "People": EXAMPLE_TABS["People"]}
    assert parse_schedule(no_hpcs_tab, MON).problems[0] == 'The sheet has no "HPCs" tab.'


def test_real_google_export():
    tabs = read_workbook((Path(__file__).parent / "fixtures" / "google_export.xlsx").read_bytes())
    assert tabs["Runs"][0] == ("Person", "Description", "HPC", "Start date", "End date")
    s = parse_schedule(tabs, MON)
    assert (s.people, s.hpcs, s.runs) == ([], [], [])
    assert s.problems == ["No admin is ticked on the People tab.", "Row 2 (?, ?): no person given; no HPC given, so it was skipped."]
