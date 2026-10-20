"""Shared test data and helpers."""

import io
from datetime import date, datetime as D

import openpyxl

MON = date(2026, 10, 19)

# The example sheet from the design spec, with the tidied People and HPCs tabs.
EXAMPLE_TABS = {
    "Runs": [
        ["Person", "Description", "HPC", "Start date", "End date"],
        ["Alex", "Hikurangi rupture scenarios", "Mahuika", D(2026, 10, 12), D(2026, 11, 1)],
        ["Sam", "Kaikōura validation runs", "Frontera", D(2026, 10, 19), D(2026, 10, 23)],
        ["Jordan", "Alpine Fault ensemble, part 2", "Mahuika", D(2026, 10, 26), D(2026, 11, 13)],
        ["Riley", "Velocity model sensitivity tests", "Setonix", D(2026, 10, 28), D(2026, 11, 6)],
        ["Casey", "Site response tests", "Frontera", "early Nov", D(2026, 11, 13)],
    ],
    "People": [["Name"], ["Alex"], ["Sam"], ["Jordan"], ["Riley"], ["Casey"], ["Morgan"]],
    "HPCs": [["HPC"], ["Mahuika"], ["Frontera"], ["Setonix"], ["Test cluster"]],
}


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
    """The parts of a requests.Response that hpc_gantt reads."""

    def __init__(self, status_code=200, headers=None, content=b""):
        self.status_code, self.headers, self.content = status_code, headers or {}, content
