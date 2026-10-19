"""Shared test data and helpers."""

import io
from datetime import date, datetime as D

import openpyxl

MON = date(2026, 10, 19)

# The example sheet from the design spec.
EXAMPLE_TABS = {
    "Runs": [
        ["Person", "Description", "HPC", "Start date", "End date"],
        ["Alex", "Hikurangi rupture scenarios", "Mahuika", D(2026, 10, 12), D(2026, 11, 1)],
        ["Sam", "Kaikōura validation runs", "Frontera", D(2026, 10, 19), D(2026, 10, 23)],
        ["Jordan", "Alpine Fault ensemble, part 2", "Mahuika", D(2026, 10, 26), D(2026, 11, 13)],
        ["Riley", "Velocity model sensitivity tests", "Setonix", D(2026, 10, 28), D(2026, 11, 6)],
        ["Casey", "Site response tests", "Frontera", "early Nov", D(2026, 11, 13)],
    ],
    "People": [
        ["Name", "Slack member ID", "Admin"],
        ["Alex", "U04ABC1DEF", False], ["Sam", "U04GHI2JKL", False], ["Jordan", "U05MNO3PQR", False],
        ["Riley", "U05STU4VWX", False], ["Casey", "U06YZA5BCD", False], ["Morgan", "U06EFG6HIJ", True],
    ],
    "HPCs": [["HPC", "Alert if idle"], ["Mahuika", True], ["Frontera", True], ["Setonix", True], ["Test cluster", False]],
}


LINK = "https://docs.google.com/spreadsheets/d/SHEET_ID/edit"

# The posts the design spec shows for EXAMPLE_TABS (Monday 19 Oct and Friday 23 Oct).
EXPECTED_WEEKLY = f"""\
:spiral_calendar_pad: *HPC plan for this week* · Mon 19 – Sun 25 Oct

*Mahuika*
• <@U04ABC1DEF> — Hikurangi rupture scenarios (12 Oct – 1 Nov)
*Frontera*
• <@U04GHI2JKL> — Kaikōura validation runs (19 – 23 Oct)

:warning: <@U06EFG6HIJ> nothing is planned on:
• *Setonix* this week
• *Frontera* next week (26 Oct – 1 Nov)

Plans changed? <{LINK}|Update the sheet>"""

EXPECTED_HEADS_UP = f"""\
:eyes: *Heads-up: starting next week* · Mon 26 Oct – Sun 1 Nov

*Mahuika*
• <@U05MNO3PQR> — Alpine Fault ensemble, part 2 (26 Oct – 13 Nov)
*Setonix*
• <@U05STU4VWX> — Velocity model sensitivity tests (28 Oct – 6 Nov)

Plans changed? <{LINK}|Update the sheet>"""

EXPECTED_REPLY = """\
<@U06EFG6HIJ> 1 problem in the sheet needs fixing:
• Row 6 (Casey, Frontera): start date "early Nov" isn't a date, so it was skipped."""


def make_xlsx(tabs):
    """Build an .xlsx file in memory with one sheet per tab."""
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for title, rows in tabs.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def with_runs(*rows):
    """Return EXAMPLE_TABS with its Runs rows replaced by ``rows`` (header kept)."""
    return {**EXAMPLE_TABS, "Runs": [EXAMPLE_TABS["Runs"][0], *rows]}


class FakeResponse:
    """The parts of a requests.Response that hpc_reminder reads."""

    def __init__(self, status_code=200, headers=None, content=b"", json_data=None):
        self.status_code, self.headers, self.content, self._json = status_code, headers or {}, content, json_data

    def json(self):
        return self._json
