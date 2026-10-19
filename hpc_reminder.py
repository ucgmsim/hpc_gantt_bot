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

import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import openpyxl

NZ = ZoneInfo("Pacific/Auckland")

# Each tab of the planning sheet and the columns the bot reads from it.
TABS = {
    "Runs": ["Person", "Description", "HPC", "Start date", "End date"],
    "People": ["Name", "Slack member ID", "Admin"],
    "HPCs": ["HPC", "Alert if idle"],
}
MEMBER_ID = re.compile(r"[UW][A-Z0-9]{6,}")


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


# ---------------------------------------------------------------- the sheet


class SheetError(Exception):
    """The planning sheet couldn't be downloaded or opened."""


@dataclass(frozen=True)
class Person:
    name: str
    member_id: str
    admin: bool


@dataclass(frozen=True)
class Hpc:
    name: str
    watched: bool  # "Alert if idle" is ticked


@dataclass(frozen=True)
class Run:
    row: int  # the sheet's own row number (header = 1)
    person: Person
    description: str
    hpc: str
    start: date
    end: date  # inclusive


@dataclass(frozen=True)
class Schedule:
    """The usable contents of the sheet, plus a line for everything that wasn't usable."""

    people: list[Person]
    hpcs: list[Hpc]
    runs: list[Run]
    problems: list[str]

    @property
    def admins(self) -> list[Person]:
        return [person for person in self.people if person.admin]


def read_workbook(xlsx: bytes) -> dict[str, list[tuple]]:
    """Return every tab of an .xlsx file as a list of row tuples, header row included."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True, data_only=True)
        try:
            return {sheet.title: list(sheet.iter_rows(values_only=True)) for sheet in workbook.worksheets}
        finally:
            workbook.close()
    except Exception as exc:
        raise SheetError(f"couldn't open the downloaded spreadsheet: {exc}") from exc


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _key(value: object) -> str:
    """Normalise a name for matching, ignoring case and surrounding spaces."""
    return _text(value).casefold()


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _records(
    tabs: Mapping[str, Sequence[Sequence[object]]], problems: list[str]
) -> dict[str, list[tuple[int, dict[str, object]]]]:
    """Return each tab's data rows as (sheet row number, {column: value}).

    A missing tab or column is added to ``problems`` and that tab is treated as empty.
    """
    by_key = {_key(title): rows for title, rows in tabs.items()}
    records = {}
    for tab, columns in TABS.items():
        rows = by_key.get(_key(tab))
        if rows is None:
            problems.append(f'The sheet has no "{tab}" tab.')
            records[tab] = []
            continue
        header = [_key(cell) for cell in rows[0]] if rows else []
        missing = [column for column in columns if _key(column) not in header]
        if missing:
            problems.extend(f'The {tab} tab has no "{column}" column.' for column in missing)
            records[tab] = []
            continue
        index = {column: header.index(_key(column)) for column in columns}
        records[tab] = [
            (number, {column: row[i] if i < len(row) else None for column, i in index.items()})
            for number, row in enumerate(rows[1:], start=2)
        ]
    return records


def parse_schedule(tabs: Mapping[str, Sequence[Sequence[object]]], this_monday: date) -> Schedule:
    """Turn the sheet's tabs into a Schedule, skipping and reporting anything unusable.

    Parameters
    ----------
    tabs
        Tab title to rows, as returned by `read_workbook`.
    this_monday
        Monday of the current week. Runs that ended before it are ignored unchecked.
    """
    problems: list[str] = []
    records = _records(tabs, problems)

    people: dict[str, Person] = {}
    seen: set[str] = set()
    for number, record in records["People"]:
        name = _text(record["Name"])
        if not name:
            continue
        if _key(name) in seen:
            problems.append(f'People row {number}: "{name}" is already listed above, so this row was skipped.')
            continue
        seen.add(_key(name))
        member_id = _text(record["Slack member ID"])
        if not member_id:
            problems.append(f"People row {number} ({name}): no Slack member ID, so this row was skipped.")
        elif not MEMBER_ID.fullmatch(member_id):
            problems.append(f'People row {number} ({name}): "{member_id}" isn\'t a Slack member ID, so this row was skipped.')
        else:
            people[_key(name)] = Person(name, member_id, record["Admin"] is True)
    if not any(person.admin for person in people.values()):
        problems.append("No admin is ticked on the People tab.")

    hpcs: dict[str, Hpc] = {}
    for number, record in records["HPCs"]:
        name = _text(record["HPC"])
        if not name:
            continue
        if _key(name) in hpcs:
            problems.append(f'HPCs row {number}: "{name}" is already listed above, so this row was skipped.')
            continue
        hpcs[_key(name)] = Hpc(name, record["Alert if idle"] is True)

    runs: list[Run] = []
    for number, record in records["Runs"]:
        if not any(_text(record[column]) for column in TABS["Runs"]):
            continue
        start, end = _as_date(record["Start date"]), _as_date(record["End date"])
        if end is not None and end < this_monday:
            continue
        person_text, hpc_text = _text(record["Person"]), _text(record["HPC"])
        person, hpc = people.get(_key(person_text)), hpcs.get(_key(hpc_text))
        reasons = []
        if not person_text:
            reasons.append("no person given")
        elif person is None:
            reasons.append(f'"{person_text}" isn\'t on the People tab with a valid Slack member ID')
        if not hpc_text:
            reasons.append("no HPC given")
        elif hpc is None:
            reasons.append(f'HPC "{hpc_text}" isn\'t on the HPCs tab')
        for label, column, parsed in (("start date", "Start date", start), ("end date", "End date", end)):
            if not _text(record[column]):
                reasons.append(f"{label} is empty")
            elif parsed is None:
                reasons.append(f'{label} "{_text(record[column])}" isn\'t a date')
        if start and end and start > end:
            reasons.append("start date is after the end date")
        if reasons:
            problems.append(f"Row {number} ({person_text or '?'}, {hpc_text or '?'}): {'; '.join(reasons)}, so it was skipped.")
        else:
            runs.append(Run(number, person, _text(record["Description"]), hpc.name, start, end))

    return Schedule(list(people.values()), list(hpcs.values()), runs, problems)
