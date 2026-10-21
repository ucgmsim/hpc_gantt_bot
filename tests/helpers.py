"""Shared test data and helpers."""

import io
import struct
from datetime import date, datetime as D

import openpyxl

from hpc_gantt import NZ

MON = date(2026, 10, 19)
TUE = date(2026, 10, 20)
NOW = D(2026, 10, 20, 14, 0, tzinfo=NZ)

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


def png_size(path):
    """Return a PNG file's (width, height), failing the test if the file isn't a PNG."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])
