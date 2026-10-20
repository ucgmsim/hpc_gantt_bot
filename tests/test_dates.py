from datetime import date, datetime, timezone

import pytest

from hpc_gantt import format_date_range, nz_today, week_monday


@pytest.mark.parametrize("day", [date(2026, 10, 19), date(2026, 10, 21), date(2026, 10, 25)])
def test_week_monday(day):
    assert week_monday(day) == date(2026, 10, 19)


@pytest.mark.parametrize("start, end, text", [
    (date(2026, 10, 19), date(2026, 10, 19), "19 Oct"),
    (date(2026, 10, 19), date(2026, 10, 23), "19 – 23 Oct"),
    (date(2026, 10, 12), date(2026, 11, 1), "12 Oct – 1 Nov"),
    (date(2026, 12, 28), date(2027, 1, 8), "28 Dec 2026 – 8 Jan 2027"),
])
def test_format_date_range(start, end, text):
    assert format_date_range(start, end) == text


def test_nz_today_uses_new_zealand_dates():
    # 09:30 Monday in NZDT (UTC+13) and in NZST (UTC+12)
    assert nz_today(datetime(2026, 10, 18, 20, 30, tzinfo=timezone.utc)) == date(2026, 10, 19)
    assert nz_today(datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)) == date(2026, 7, 6)
