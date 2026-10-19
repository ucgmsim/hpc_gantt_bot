#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "cyclopts",
#   "openpyxl",
#   "requests",
# ]
# ///
"""Post HPC usage reminders from the team's planning sheet to Slack."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

NZ = ZoneInfo("Pacific/Auckland")


# ---------------------------------------------------------------- dates


def week_monday(day: date) -> date:
    """Return the Monday of the Monday-to-Sunday week that contains ``day``."""
    return day - timedelta(days=day.weekday())


def _span(start: date, end: date, first: str = "", last: str = "") -> str:
    """Format two different dates, naming the month and year only as often as needed."""
    if start.year != end.year:
        return f"{first}{start.day} {start:%b %Y} – {last}{end.day} {end:%b %Y}"
    if start.month != end.month:
        return f"{first}{start.day} {start:%b} – {last}{end.day} {end:%b}"
    return f"{first}{start.day} – {last}{end.day} {end:%b}"


def format_date_range(start: date, end: date) -> str:
    """Format an inclusive date range, e.g. ``12 Oct – 1 Nov``."""
    if start == end:
        return f"{start.day} {start:%b}"
    return _span(start, end)


def format_week(monday: date) -> str:
    """Format the week starting ``monday``, e.g. ``Mon 19 – Sun 25 Oct``."""
    return _span(monday, monday + timedelta(days=6), "Mon ", "Sun ")


def nz_today(now: datetime | None = None) -> date:
    """Return today's date in New Zealand (``now`` must be timezone-aware)."""
    return (now or datetime.now(NZ)).astimezone(NZ).date()
