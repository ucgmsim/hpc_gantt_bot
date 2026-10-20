#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "cyclopts",
#   "matplotlib",
#   "openpyxl",
#   "requests",
# ]
# ///
"""Draw the team's HPC usage plan as a Gantt chart and upload it to Dropbox."""

import io
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")  # draw to files only; mantle has no display

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import openpyxl
import requests
from matplotlib.patches import BoxStyle, FancyBboxPatch, Patch

NZ = ZoneInfo("Pacific/Auckland")

# Each tab of the planning sheet and the columns the bot reads from it.
TABS = {
    "Runs": ["Person", "Description", "HPC", "Start date", "End date"],
    "People": ["Name"],
    "HPCs": ["HPC"],
}


# ---------------------------------------------------------------- dates


def week_monday(day: date) -> date:
    """Return the Monday of the Monday-to-Sunday week that contains ``day``."""
    return day - timedelta(days=day.weekday())


def format_date_range(start: date, end: date) -> str:
    """Format an inclusive date range, e.g. ``12 Oct – 1 Nov``, naming months and years only as needed."""
    if start == end:
        return f"{start.day} {start:%b}"
    if start.year != end.year:
        return f"{start.day} {start:%b %Y} – {end.day} {end:%b %Y}"
    if start.month != end.month:
        return f"{start.day} {start:%b} – {end.day} {end:%b}"
    return f"{start.day} – {end.day} {end:%b}"


def nz_today(now: datetime | None = None) -> date:
    """Return today's date in New Zealand (``now`` must be timezone-aware)."""
    return (now or datetime.now(NZ)).astimezone(NZ).date()


# ---------------------------------------------------------------- the sheet


class SheetError(Exception):
    """The planning sheet couldn't be downloaded or opened."""


@dataclass(frozen=True)
class Run:
    row: int  # the sheet's own row number (header = 1)
    person: str  # as written on the People tab
    description: str
    hpc: str  # as written on the HPCs tab
    start: date
    end: date  # inclusive


@dataclass(frozen=True)
class Schedule:
    """The usable contents of the sheet, plus a line for everything that wasn't usable."""

    people: list[str]
    hpcs: list[str]
    runs: list[Run]
    problems: list[str]


class _Transient(Exception):
    """An HTTP response worth retrying (429 or 5xx)."""

    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def _checked(response: requests.Response) -> requests.Response:
    if response.status_code == 429 or response.status_code >= 500:
        raise _Transient(response.status_code)
    return response


def with_retries[T](call: Callable[[], T], attempts: int = 3, wait_seconds: float = 5.0) -> T:
    """Run ``call``, retrying network failures and 429/5xx responses."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except (requests.ConnectionError, requests.Timeout, _Transient):
            if attempt == attempts:
                raise
            time.sleep(wait_seconds)
    raise AssertionError("attempts must be at least 1")


def download_workbook(sheet_id: str) -> bytes:
    """Download the planning sheet as .xlsx, without credentials (it is link-shared)."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    try:
        response = with_retries(lambda: _checked(requests.get(url, timeout=30)))
    except _Transient as exc:
        raise SheetError(f"download failed with HTTP {exc.status_code}") from exc
    except requests.RequestException as exc:
        raise SheetError(f"download failed: {exc}") from exc
    if response.status_code != 200:
        raise SheetError(f"download failed with HTTP {response.status_code}")
    if "spreadsheetml" not in response.headers.get("Content-Type", ""):
        raise SheetError("the download wasn't a spreadsheet; check the sheet is shared as \"Anyone with the link can view\"")
    return response.content


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
            problems.append(f'The sheet has no "{tab}" tab')
            records[tab] = []
            continue
        header = [_key(cell) for cell in rows[0]] if rows else []
        missing = [column for column in columns if _key(column) not in header]
        if missing:
            problems.extend(f'The {tab} tab has no "{column}" column' for column in missing)
            records[tab] = []
            continue
        index = {column: header.index(_key(column)) for column in columns}
        records[tab] = [
            (number, {column: row[i] if i < len(row) else None for column, i in index.items()})
            for number, row in enumerate(rows[1:], start=2)
        ]
    return records


def _names(records: list[tuple[int, dict[str, object]]], column: str, tab: str, problems: list[str]) -> dict[str, str]:
    """Collect the names in one column of a list tab, keyed for matching; repeats become problems."""
    names: dict[str, str] = {}
    for number, record in records:
        name = _text(record[column])
        if not name:
            continue
        if _key(name) in names:
            problems.append(f'{tab} row {number}: "{name}" is listed twice')
            continue
        names[_key(name)] = name
    return names


def parse_schedule(tabs: Mapping[str, Sequence[Sequence[object]]], first_day: date) -> Schedule:
    """Turn the sheet's tabs into a Schedule, skipping and reporting anything unusable.

    Parameters
    ----------
    tabs
        Tab title to rows, as returned by `read_workbook`.
    first_day
        First day the chart shows. Runs that ended before it are ignored unchecked.
    """
    problems: list[str] = []
    records = _records(tabs, problems)
    people = _names(records["People"], "Name", "People", problems)
    hpcs = _names(records["HPCs"], "HPC", "HPCs", problems)

    runs: list[Run] = []
    for number, record in records["Runs"]:
        if not any(_text(record[column]) for column in TABS["Runs"]):
            continue
        start, end = _as_date(record["Start date"]), _as_date(record["End date"])
        # Finished runs aren't checked, unless the dates are reversed: then the end date is the mistake.
        if end is not None and end < first_day and not (start is not None and start > end):
            continue
        person_text, hpc_text = _text(record["Person"]), _text(record["HPC"])
        person, hpc = people.get(_key(person_text)), hpcs.get(_key(hpc_text))
        reasons = []
        if not person_text:
            reasons.append("no person given")
        elif person is None:
            reasons.append(f'"{person_text}" isn\'t on the People tab')
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
            problems.append(f"Row {number} ({person_text or '?'}, {hpc_text or '?'}): {'; '.join(reasons)}")
        else:
            runs.append(Run(number, person, _text(record["Description"]), hpc, start, end))

    return Schedule(list(people.values()), list(hpcs.values()), runs, problems)


# ---------------------------------------------------------------- chart layout


@dataclass(frozen=True)
class Bar:
    """One run as drawn: its dates cut to the chart, plus its caption and where the caption goes."""

    row: int  # 0 = top row of the chart
    start: date  # first day drawn
    end: date  # day after the last day drawn
    cut_start: bool  # the run began before the chart's first day
    cut_end: bool  # the run continues past the chart's end
    finished: bool  # the run ended before today
    caption: str
    label_x: date  # where the caption is anchored
    label_align: str  # "left" or "right"


@dataclass(frozen=True)
class Lane:
    hpc: str
    top_row: int
    rows: int  # at least 1: an empty lane still gets a row
    empty: bool


@dataclass(frozen=True)
class Layout:
    """Everything the chart shows, worked out before anything is drawn."""

    first_day: date
    end: date  # the day after the last day shown
    today: date
    lanes: list[Lane]
    bars: list[Bar]
    problems: list[str]

    @property
    def rows(self) -> int:
        return sum(lane.rows for lane in self.lanes)


def chart_window(today: date) -> tuple[date, date]:
    """Return (first day, day after the last day): from 2 weeks before this week's Monday to 13 weeks after it."""
    monday = week_monday(today)
    return monday - timedelta(weeks=2), monday + timedelta(weeks=13)


def caption(person: str, description: str, max_chars: int = 60) -> str:
    """The text shown with a run's bar, shortened with "…" if it is too long."""
    text = f"{person} · {description}" if description else person
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def layout_chart(schedule: Schedule, today: date) -> Layout:
    """Give every run that falls within the chart its own row, grouped into one lane per HPC."""
    first_day, end = chart_window(today)
    late = first_day + timedelta(days=70)  # bars starting this late get right-aligned captions
    lanes, bars, row = [], [], 0
    for hpc in schedule.hpcs:
        runs = sorted(
            (run for run in schedule.runs if run.hpc == hpc and run.start < end and run.end >= first_day),
            key=lambda run: (run.start, run.person.casefold(), run.row),
        )
        lanes.append(Lane(hpc, row, max(len(runs), 1), not runs))
        for run in runs:
            day_after = run.end + timedelta(days=1)
            start, stop = max(run.start, first_day), min(day_after, end)
            right = start >= late
            bars.append(Bar(
                row, start, stop, run.start < first_day, day_after > end, run.end < today,
                caption(run.person, run.description), stop if right else start, "right" if right else "left",
            ))
            row += 1
        if not runs:
            row += 1
    return Layout(first_day, end, today, lanes, bars, schedule.problems)


# ---------------------------------------------------------------- drawing

# Colours from the dataviz reference palette (light surface).
SURFACE, INK, INK_SECONDARY, INK_MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRIDLINE, DIVIDER = "#e1e0d9", "#c3c2b7"
CURRENT, FINISHED = "#2a78d6", "#c3c2b7"

DPI = 120
WIDTH = 14.0  # inches, so the PNG is 1680 px wide
ROW = 0.42  # inches per row
LEFT, RIGHT = 1.7, 0.35  # inches beside the plot: HPC names on the left, breathing room on the right
TOP = 1.45  # inches above the plot: title, subtitle, legend, week labels and "today"


# Text drawn over the plot sits on a patch of background, so gridlines and the today line never cross it.
TEXT_BACKGROUND = {"boxstyle": "square,pad=0.15", "facecolor": SURFACE, "edgecolor": "none"}


def _pt(pixels: float) -> float:
    """Convert pixels to points at the chart's resolution, for line widths."""
    return pixels * 72 / DPI


def chart_subtitle(first_day: date, end: date, updated: datetime) -> str:
    """The line under the title: when the chart was made and which dates it shows."""
    stamp = f"{updated:%a} {updated.day} {updated:%b %Y, %H:%M %Z}"
    return f"Updated {stamp} · showing {format_date_range(first_day, end - timedelta(days=1))}"


def footer_lines(problems: list[str], limit: int = 8) -> list[str]:
    """The small print under the chart, listing at most ``limit`` problems in the sheet."""
    if not problems:
        return []
    lines = ["Problems in the sheet:", *problems[:limit]]
    if len(problems) > limit:
        lines.append(f"…and {len(problems) - limit} more")
    return lines


def draw_chart(layout: Layout, updated: datetime, output: Path) -> None:
    """Draw the layout as a PNG Gantt chart at ``output``."""
    rows = max(layout.rows, 1)
    footer = footer_lines(layout.problems)
    bottom = 0.3 + 0.17 * len(footer) + 0.3  # inches below the plot: problems, then the source line
    height = TOP + rows * ROW + bottom
    fig = plt.figure(figsize=(WIDTH, height), dpi=DPI, facecolor=SURFACE)
    ax = fig.add_axes((LEFT / WIDTH, bottom / height, 1 - (LEFT + RIGHT) / WIDTH, rows * ROW / height))
    ax.set_facecolor(SURFACE)
    x0, x1 = mdates.date2num(layout.first_day), mdates.date2num(layout.end)
    ax.set_xlim(x0, x1)
    ax.set_ylim(rows, 0)  # row 0 at the top
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_yticks([])

    # Week lines at every Monday, labelled along the top.
    mondays = [layout.first_day + timedelta(weeks=i) for i in range((layout.end - layout.first_day).days // 7)]
    for monday in mondays:
        ax.axvline(mdates.date2num(monday), color=GRIDLINE, linewidth=_pt(1), zorder=0)
    ax.xaxis.tick_top()
    ax.set_xticks([mdates.date2num(m) for m in mondays], [f"{m.day} {m:%b}" for m in mondays])
    ax.tick_params(axis="x", length=0, pad=14, labelsize=8, labelcolor=INK_MUTED)

    # Lanes: the HPC name on the left, a divider between lanes, and a note in empty ones.
    names_x = ax.get_yaxis_transform()  # x in axes fraction, y in rows
    for i, lane in enumerate(layout.lanes):
        if i:
            ax.axhline(lane.top_row, color=DIVIDER, linewidth=_pt(1), zorder=1)
        ax.text(-0.012, lane.top_row + 0.5, lane.hpc, transform=names_x, ha="right", va="center",
                fontsize=10, fontweight="bold", color=INK)
        if lane.empty:
            ax.text(x0 + 0.5, lane.top_row + 0.5, "nothing planned", ha="left", va="center",
                    fontsize=9, style="italic", color=INK_MUTED, bbox=TEXT_BACKGROUND, zorder=5)
    if not layout.lanes:
        ax.text(0.5, 0.5, "No HPCs listed yet. Add them to the HPCs tab of the sheet.", transform=ax.transAxes,
                ha="center", va="center", fontsize=11, color=INK_SECONDARY, bbox=TEXT_BACKGROUND, zorder=5)

    # Bars: thin, with 4 px rounded ends. A cut end runs past the plot edge, where clipping squares it off.
    x_per_px = (x1 - x0) / ((WIDTH - LEFT - RIGHT) * DPI)
    y_per_px = 1 / (ROW * DPI)
    for bar in layout.bars:
        left = mdates.date2num(bar.start) - (6 * x_per_px if bar.cut_start else 0)
        right = mdates.date2num(bar.end) + (6 * x_per_px if bar.cut_end else 0)
        ax.add_patch(FancyBboxPatch(
            (left, bar.row + 0.62), right - left, 10 * y_per_px,
            boxstyle=BoxStyle.Round(pad=0, rounding_size=4 * x_per_px), mutation_aspect=y_per_px / x_per_px,
            facecolor=FINISHED if bar.finished else CURRENT, edgecolor="none", linewidth=0, zorder=2,
        ))
        ax.text(mdates.date2num(bar.label_x), bar.row + 0.55, bar.caption, ha=bar.label_align, va="bottom",
                fontsize=9, color=INK, bbox=TEXT_BACKGROUND, zorder=5)

    # Today: a line at the start of today, so every finished bar ends at or before it.
    today = mdates.date2num(layout.today)
    ax.axvline(today, color=INK, linewidth=_pt(1.5), zorder=3)  # over the bars, under the text
    ax.text(today, 0, " today", ha="left", va="bottom", fontsize=8, color=INK, clip_on=False)

    # Title, subtitle and legend.
    margin = 0.25 / WIDTH
    fig.text(margin, 1 - 0.22 / height, "HPC usage plan", ha="left", va="top", fontsize=16, color=INK)
    fig.text(margin, 1 - 0.6 / height, chart_subtitle(layout.first_day, layout.end, updated),
             ha="left", va="top", fontsize=10, color=INK_SECONDARY)
    fig.legend(
        handles=[Patch(facecolor=CURRENT, edgecolor="none", label="underway or upcoming"),
                 Patch(facecolor=FINISHED, edgecolor="none", label="finished")],
        loc="upper right", bbox_to_anchor=(1 - RIGHT / WIDTH, 1 - 0.2 / height), ncols=2, frameon=False,
        fontsize=9, labelcolor=INK_SECONDARY, handlelength=1.2, handleheight=0.8,
    )

    # Footer: problems in the sheet, then where the data comes from.
    if footer:
        fig.text(margin, (bottom - 0.25) / height, "\n".join(footer), ha="left", va="top", fontsize=8,
                 color=INK_SECONDARY, linespacing=1.5)
    fig.text(margin, 0.12 / height, "Source: the HPC usage plan Google Sheet", ha="left", va="bottom",
             fontsize=8, color=INK_MUTED)

    fig.savefig(output, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
