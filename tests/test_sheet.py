from datetime import date, datetime as D
from pathlib import Path

import pytest

from helpers import EXAMPLE_TABS, MON, make_xlsx, with_runs
from hpc_gantt import Run, SheetError, parse_schedule, read_workbook

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
    assert s.runs[0] == Run(2, "Alex", "Hikurangi rupture scenarios", "Mahuika", date(2026, 10, 12), date(2026, 11, 1))
    assert s.people == ["Alex", "Sam", "Jordan", "Riley", "Casey", "Morgan"]
    assert s.hpcs == ["Mahuika", "Frontera", "Setonix", "Test cluster"]
    assert s.problems == ['Row 6 (Casey, Frontera): start date "early Nov" isn\'t a date']


def test_names_match_ignoring_case_and_spaces():
    run = parse_schedule(with_runs([" alex ", None, "mahuika ", d1, d2]), MON).runs[0]
    assert (run.person, run.hpc, run.description) == ("Alex", "Mahuika", "")


def test_extra_columns_and_tab_spelling_are_ignored():
    tabs = {"runs": [["Person", "Description", "HPC", "Start date", "End date"]],
            "people": [["Slack member ID", " NAME ", "Admin"], ["U04ABC1DEF", "Alex", True]],
            "HPCs": [["Alert if idle", "HPC"], [True, "Mahuika"]]}
    s = parse_schedule(tabs, MON)
    assert (s.people, s.hpcs, s.problems) == (["Alex"], ["Mahuika"], [])


def test_blank_rows_are_ignored():
    tabs = with_runs([None] * 5, ["  ", None, "", None, None])
    tabs["People"] = tabs["People"] + [[None]]
    tabs["HPCs"] = tabs["HPCs"] + [[None]]
    s = parse_schedule(tabs, MON)
    assert (s.runs, s.problems) == ([], [])


@pytest.mark.parametrize("row, problem", [
    (["Jamie", "x", "Mahuika", d1, d2], 'Row 2 (Jamie, Mahuika): "Jamie" isn\'t on the People tab'),
    (["Alex", "x", "Kupe", d1, d2], 'Row 2 (Alex, Kupe): HPC "Kupe" isn\'t on the HPCs tab'),
    ([None, "x", "Mahuika", d1, d2], "Row 2 (?, Mahuika): no person given"),
    (["Alex", "x", "Mahuika", d2, d1], "Row 2 (Alex, Mahuika): start date is after the end date"),
    (["Alex", "x", "Mahuika", d1, None], "Row 2 (Alex, Mahuika): end date is empty"),
    (["Jamie", "x", "Kupe", d1, d2], 'Row 2 (Jamie, Kupe): "Jamie" isn\'t on the People tab; HPC "Kupe" isn\'t on the HPCs tab'),
])
def test_bad_rows_are_reported_and_skipped(row, problem):
    s = parse_schedule(with_runs(row), MON)
    assert (s.runs, s.problems) == ([], [problem])


def test_rows_that_ended_before_the_first_day_are_not_checked():
    s = parse_schedule(with_runs(["Jamie", "x", "Kupe", "early Oct", D(2026, 10, 18)]), MON)
    assert (s.runs, s.problems) == ([], [])


def test_unreadable_end_date_is_always_reported():
    s = parse_schedule(with_runs(["Alex", "x", "Mahuika", D(2026, 10, 1), "whenever"]), MON)
    assert s.problems == ['Row 2 (Alex, Mahuika): end date "whenever" isn\'t a date']


def test_reversed_dates_are_reported_even_when_the_end_is_past():
    s = parse_schedule(with_runs(["Alex", "x", "Mahuika", D(2026, 12, 28), D(2026, 1, 8)]), date(2026, 12, 21))
    assert (s.runs, s.problems) == ([], ["Row 2 (Alex, Mahuika): start date is after the end date"])


def test_sheet_level_problems():
    tabs = {"People": [["Name"], ["Alex"], ["alex"]], "HPCs": [["HPC"], ["Mahuika"], ["MAHUIKA"]],
            "Runs": [["Person", "Description", "HPC", "Start date"]]}
    assert parse_schedule(tabs, MON).problems == [
        'The Runs tab has no "End date" column',
        'People row 3: "alex" is listed twice',
        'HPCs row 3: "MAHUIKA" is listed twice',
    ]
    assert parse_schedule({"Runs": EXAMPLE_TABS["Runs"], "People": EXAMPLE_TABS["People"]}, MON).problems[0] == 'The sheet has no "HPCs" tab'


def test_real_google_export():
    tabs = read_workbook((Path(__file__).parent / "fixtures" / "google_export.xlsx").read_bytes())
    s = parse_schedule(tabs, MON)
    assert (s.people, s.hpcs, s.runs) == ([], [], [])
    assert s.problems == ["Row 2 (?, ?): no person given; no HPC given"]


def test_line_breaks_in_cells_are_collapsed():
    # Alt+Enter in a cell must not turn a caption into several lines that climb into the row above
    run = parse_schedule(with_runs(["Alex", "Hikurangi scenarios\nphase 2\n(see  Slack)", "Mahuika", d1, d2]), MON).runs[0]
    assert run.description == "Hikurangi scenarios phase 2 (see Slack)"
