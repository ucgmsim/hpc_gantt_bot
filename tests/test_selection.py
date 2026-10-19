from datetime import date

import pytest

from hpc_reminder import Person, Run, idle_hpcs, overlaps, runs_in_week, runs_starting_in_week

ALEX = Person("Alex", "U04ABC1DEF", False)


def test_runs_in_week(example_schedule):
    assert [r.row for r in runs_in_week(example_schedule, date(2026, 10, 19))] == [2, 3]
    assert [r.row for r in runs_in_week(example_schedule, date(2026, 10, 26))] == [2, 4, 5]


def test_runs_starting_in_week(example_schedule):
    assert [r.row for r in runs_starting_in_week(example_schedule, date(2026, 10, 26))] == [4, 5]


def test_idle_hpcs(example_schedule):
    assert idle_hpcs(example_schedule, date(2026, 10, 19)) == ["Setonix"]
    # Casey's skipped row doesn't cover Frontera; Test cluster isn't watched
    assert idle_hpcs(example_schedule, date(2026, 10, 26)) == ["Frontera"]


@pytest.mark.parametrize("start, end, expected", [
    (date(2026, 10, 12), date(2026, 10, 19), True),   # ends on the Monday
    (date(2026, 10, 25), date(2026, 11, 2), True),    # starts on the Sunday
    (date(2026, 10, 12), date(2026, 10, 18), False),  # ended the Sunday before
    (date(2026, 10, 26), date(2026, 10, 30), False),  # starts the Monday after
    (date(2026, 10, 1), date(2026, 12, 31), True),    # spans the whole week
])
def test_overlaps(start, end, expected):
    assert overlaps(Run(2, ALEX, "", "Mahuika", start, end), date(2026, 10, 19)) is expected


def test_new_year_week():
    run = Run(2, ALEX, "", "Mahuika", date(2026, 12, 31), date(2027, 1, 2))
    assert overlaps(run, date(2026, 12, 28)) and not overlaps(run, date(2027, 1, 4))
