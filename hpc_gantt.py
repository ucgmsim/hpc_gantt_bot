"""Draw the team's HPC usage plan as a Gantt chart and upload it to Dropbox."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib
import matplotlib.dates as mdates
import openpyxl
import requests
from cyclopts import App
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch, Patch

matplotlib.rcParams["text.parse_math"] = (
    False  # sheet text like "$SCRATCH to $PROJECT" is not maths
)

NZ = ZoneInfo("Pacific/Auckland")

# Each tab of the planning sheet and the columns the bot reads from it.
TABS = {
    "Runs": ["Person", "Description", "HPC", "Start date", "End date"],
    "People": ["Name"],
    "HPCs": ["HPC"],
}


# ---------------------------------------------------------------- dates


def week_monday(day: date) -> date:
    """Return the Monday of the Monday-to-Sunday week that contains ``day``.

    Parameters
    ----------
    day : date
        Any day.

    Returns
    -------
    date
        The Monday on or before ``day``.
    """
    return day - timedelta(days=day.weekday())


def format_date_range(start: date, end: date) -> str:
    """Format a range of days, naming the years only if they differ.

    Parameters
    ----------
    start : date
        The first day of the range.
    end : date
        The last day of the range.

    Returns
    -------
    str
        E.g. ``5 Oct – 28 Dec`` within one year, or ``5 Oct 2026 – 17 Jan 2027`` across two.
    """
    month = "%b" if start.year == end.year else "%b %Y"
    return f"{start.day} {start:{month}} – {end.day} {end:{month}}"


# ---------------------------------------------------------------- the sheet


class SheetError(Exception):
    """The planning sheet couldn't be downloaded or opened."""


@dataclass(frozen=True)
class Run:
    """One usable row of the Runs tab.

    Parameters
    ----------
    row : int
        The sheet's own row number (the header is row 1).
    person : str
        The person, as written on the People tab.
    description : str
        What the run is for; may be empty.
    hpc : str
        The HPC, as written on the HPCs tab.
    start : date
        The first day of the run.
    end : date
        The last day of the run (inclusive).
    """

    row: int
    person: str
    description: str
    hpc: str
    start: date
    end: date


@dataclass(frozen=True)
class Schedule:
    """The usable contents of the sheet, plus a line for everything that wasn't usable.

    Parameters
    ----------
    hpcs : list[str]
        The HPCs, in the order of the HPCs tab.
    runs : list[Run]
        The usable runs that end on or after the chart's first day, in sheet order.
    problems : list[str]
        One line per problem found in the sheet.
    """

    hpcs: list[str]
    runs: list[Run]
    problems: list[str]


def download_workbook(sheet_id: str) -> bytes:
    """Download the planning sheet as .xlsx, without credentials (it is link-shared).

    Network failures and 429/5xx responses are tried three times in all, five seconds apart.

    Parameters
    ----------
    sheet_id : str
        The ID from the sheet's URL.

    Returns
    -------
    bytes
        The downloaded .xlsx file.

    Raises
    ------
    SheetError
        If the download fails, or returns something other than a spreadsheet.
    """
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    for attempt in range(3):
        if attempt:
            time.sleep(5)
        try:
            response = requests.get(url, timeout=30)
        except (requests.ConnectionError, requests.Timeout) as exc:
            failure = f"download failed: {exc}"
        except requests.RequestException as exc:
            raise SheetError(f"download failed: {exc}") from exc
        else:
            if response.status_code != 429 and response.status_code < 500:
                break
            failure = f"download failed with HTTP {response.status_code}"
    else:
        raise SheetError(failure)
    if response.status_code != 200:
        raise SheetError(f"download failed with HTTP {response.status_code}")
    if "spreadsheetml" not in response.headers.get("Content-Type", ""):
        raise SheetError(
            'the download wasn\'t a spreadsheet; check the sheet is shared as "Anyone with the link can view"'
        )
    return response.content


def read_workbook(xlsx: bytes) -> dict[str, list[tuple]]:
    """Return every tab of an .xlsx file as a list of row tuples, header row included.

    Parameters
    ----------
    xlsx : bytes
        The .xlsx file.

    Returns
    -------
    dict[str, list[tuple]]
        Each tab's title and its rows.

    Raises
    ------
    SheetError
        If the file can't be opened as a spreadsheet.
    """
    try:
        with contextlib.closing(
            openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True, data_only=True)
        ) as workbook:
            return {
                sheet.title: list(sheet.iter_rows(values_only=True))
                for sheet in workbook.worksheets
            }
    except Exception as exc:
        raise SheetError(f"couldn't open the downloaded spreadsheet: {exc}") from exc


def _text(value: object) -> str:
    """Cell text on one line: line breaks and runs of spaces become single spaces.

    Parameters
    ----------
    value : object
        A cell's value; None for an empty cell.

    Returns
    -------
    str
        The text, or "" for an empty cell.
    """
    return "" if value is None else " ".join(str(value).split())


def _key(value: object) -> str:
    """Normalise a name for matching, ignoring case and surrounding spaces.

    Parameters
    ----------
    value : object
        A cell's value.

    Returns
    -------
    str
        The key to match names by.
    """
    return _text(value).casefold()


def _as_date(value: object) -> date | None:
    """Read a cell as a date.

    Parameters
    ----------
    value : object
        A cell's value. Dates from Google Sheets arrive as datetimes.

    Returns
    -------
    date or None
        The date, or None if the cell doesn't hold one.
    """
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

    Parameters
    ----------
    tabs : Mapping[str, Sequence[Sequence[object]]]
        Tab title to rows, as returned by `read_workbook`.
    problems : list[str]
        Where to add a line for each missing tab or column.

    Returns
    -------
    dict[str, list[tuple[int, dict[str, object]]]]
        Each tab in ``TABS`` and its data rows, holding only the columns the bot reads.
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
            problems.extend(
                f'The {tab} tab has no "{column}" column' for column in missing
            )
            records[tab] = []
            continue
        index = {column: header.index(_key(column)) for column in columns}
        records[tab] = [
            (
                number,
                {
                    column: row[i] if i < len(row) else None
                    for column, i in index.items()
                },
            )
            for number, row in enumerate(rows[1:], start=2)
        ]
    return records


def _names(
    records: list[tuple[int, dict[str, object]]],
    column: str,
    tab: str,
    problems: list[str],
) -> dict[str, str]:
    """Collect the names in one column of a list tab, keyed for matching; repeats become problems.

    Parameters
    ----------
    records : list[tuple[int, dict[str, object]]]
        The tab's rows, as returned by `_records`.
    column : str
        The column holding the names.
    tab : str
        The tab's name, for problem lines.
    problems : list[str]
        Where to add a line for each repeated name.

    Returns
    -------
    dict[str, str]
        Each name as written, by its matching key.
    """
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


def parse_schedule(
    tabs: Mapping[str, Sequence[Sequence[object]]], first_day: date
) -> Schedule:
    """Turn the sheet's tabs into a Schedule, skipping and reporting anything unusable.

    Parameters
    ----------
    tabs : Mapping[str, Sequence[Sequence[object]]]
        Tab title to rows, as returned by `read_workbook`.
    first_day : date
        First day the chart shows. Runs that ended before it are ignored unchecked.

    Returns
    -------
    Schedule
        The usable HPCs and runs, and a line for each problem.
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
        if (
            end is not None
            and end < first_day
            and not (start is not None and start > end)
        ):
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
        for label, column, parsed in (
            ("start date", "Start date", start),
            ("end date", "End date", end),
        ):
            if not _text(record[column]):
                reasons.append(f"{label} is empty")
            elif parsed is None:
                reasons.append(f'{label} "{_text(record[column])}" isn\'t a date')
        if start and end and start > end:
            reasons.append("start date is after the end date")
        if reasons:
            problems.append(
                f"Row {number} ({person_text or '?'}, {hpc_text or '?'}): {'; '.join(reasons)}"
            )
        else:
            assert person and hpc and start and end  # every check above passed
            runs.append(
                Run(number, person, _text(record["Description"]), hpc, start, end)
            )

    return Schedule(list(hpcs.values()), runs, problems)


# ---------------------------------------------------------------- chart layout


@dataclass(frozen=True)
class Bar:
    """One run as drawn: its whole span (the plot clips it to the chart) and its caption.

    Parameters
    ----------
    row : int
        The chart row, 0 being the top.
    start : date
        The run's first day.
    end : date
        The day after the run's last day.
    finished : bool
        Whether the run ended before today.
    caption : str
        The text shown above the bar.
    label_x : date
        Where the caption is anchored, always inside the chart.
    label_align : str
        "left" or "right".
    """

    row: int
    start: date
    end: date
    finished: bool
    caption: str
    label_x: date
    label_align: str


@dataclass(frozen=True)
class Lane:
    """One HPC's band of rows.

    Parameters
    ----------
    hpc : str
        The HPC's name.
    top_row : int
        The lane's first chart row.
    rows : int
        How many rows it has: at least 1, as an empty lane still gets a row.
    empty : bool
        Whether no runs fall within the chart.
    """

    hpc: str
    top_row: int
    rows: int
    empty: bool


@dataclass(frozen=True)
class Layout:
    """Everything the chart shows, worked out before anything is drawn.

    Parameters
    ----------
    first_day : date
        The first day shown.
    end : date
        The day after the last day shown.
    today : date
        Where the today line goes.
    lanes : list[Lane]
        One lane per HPC, top to bottom.
    bars : list[Bar]
        One bar per run within the chart.
    problems : list[str]
        Problems in the sheet, listed under the chart.
    """

    first_day: date
    end: date
    today: date
    lanes: list[Lane]
    bars: list[Bar]
    problems: list[str]

    @property
    def rows(self) -> int:
        """Count the chart's rows.

        Returns
        -------
        int
            The rows of every lane together.
        """
        return sum(lane.rows for lane in self.lanes)


def chart_window(today: date) -> tuple[date, date]:
    """Return the chart's span: from 2 weeks before this week's Monday to 13 weeks after it.

    Parameters
    ----------
    today : date
        The day the chart is drawn for.

    Returns
    -------
    first_day : date
        The first day shown.
    end : date
        The day after the last day shown.
    """
    monday = week_monday(today)
    return monday - timedelta(weeks=2), monday + timedelta(weeks=13)


def caption(person: str, description: str, max_chars: int = 60) -> str:
    """The text shown with a run's bar, shortened with "…" if it is too long.

    Parameters
    ----------
    person : str
        Who the run belongs to.
    description : str
        What it's for; may be empty.
    max_chars : int, default 60
        The longest caption allowed, "…" included.

    Returns
    -------
    str
        The person and the description, joined by " · ", or just the person if there's no description.
    """
    text = f"{person} · {description}" if description else person
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def layout_chart(schedule: Schedule, today: date) -> Layout:
    """Give every run that falls within the chart its own row, grouped into one lane per HPC.

    Parameters
    ----------
    schedule : Schedule
        The checked sheet.
    today : date
        The day the chart is drawn for.

    Returns
    -------
    Layout
        The lanes, bars and problems to draw.
    """
    first_day, end = chart_window(today)
    late = first_day + timedelta(
        days=70
    )  # bars starting this late get right-aligned captions
    lanes, bars, row = [], [], 0
    for hpc in schedule.hpcs:
        runs = sorted(
            (
                run
                for run in schedule.runs
                if run.hpc == hpc and run.start < end and run.end >= first_day
            ),
            key=lambda run: (run.start, _key(run.person), run.row),
        )
        lanes.append(Lane(hpc, row, max(len(runs), 1), not runs))
        for i, run in enumerate(runs):
            day_after = run.end + timedelta(days=1)
            shown_start, shown_end = max(run.start, first_day), min(day_after, end)
            right = shown_start >= late
            bars.append(
                Bar(
                    row + i,
                    run.start,
                    day_after,
                    run.end < today,
                    caption(run.person, run.description),
                    shown_end if right else shown_start,
                    "right" if right else "left",
                )
            )
        row += lanes[-1].rows
    return Layout(first_day, end, today, lanes, bars, schedule.problems)


# ---------------------------------------------------------------- drawing

# Colours from the dataviz reference palette (light surface).
SURFACE, INK, INK_SECONDARY, INK_MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRIDLINE, DIVIDER = "#e1e0d9", "#c3c2b7"
CURRENT, FINISHED = "#2a78d6", "#c3c2b7"

DPI = 120
WIDTH = 14.0  # inches, so the PNG is 1680 px wide
ROW = 0.42  # inches per row
LEFT, RIGHT = (
    1.7,
    0.35,
)  # inches beside the plot: HPC names on the left, breathing room on the right
TOP = 1.45  # inches above the plot: title, subtitle, legend, week labels and "today"

# Text drawn over the plot sits on a patch of background, above every line, so gridlines and the today line
# never cross it. The stacking order is: week lines 0, lane dividers 1, bars 2, today line 3, text 5.
OVER_PLOT_TEXT: dict[str, Any] = {
    "bbox": {"boxstyle": "square,pad=0.15", "facecolor": SURFACE, "edgecolor": "none"},
    "zorder": 5,
}


def _pt(pixels: float) -> float:
    """Convert pixels to points at the chart's resolution, for line widths.

    Parameters
    ----------
    pixels : float
        A length in pixels.

    Returns
    -------
    float
        The same length in points.
    """
    return pixels * 72 / DPI


def chart_subtitle(first_day: date, end: date, updated: datetime) -> str:
    """The line under the title: when the chart was made and which dates it shows.

    Parameters
    ----------
    first_day : date
        The first day shown.
    end : date
        The day after the last day shown.
    updated : datetime
        When the chart was made, in NZ time.

    Returns
    -------
    str
        E.g. "Updated Tue 20 Oct 2026, 14:00 NZDT · showing 5 Oct 2026 – 17 Jan 2027".
    """
    stamp = f"{updated:%a} {updated.day} {updated:%b %Y, %H:%M %Z}"
    return f"Updated {stamp} · showing {format_date_range(first_day, end - timedelta(days=1))}"


def footer_lines(problems: list[str], limit: int = 8) -> list[str]:
    """The small print under the chart, listing at most ``limit`` problems in the sheet.

    Parameters
    ----------
    problems : list[str]
        Problems in the sheet.
    limit : int, default 8
        How many to list before "…and N more".

    Returns
    -------
    list[str]
        The lines, or none if there are no problems.
    """
    if not problems:
        return []
    lines = ["Problems in the sheet:", *problems[:limit]]
    if len(problems) > limit:
        lines.append(f"…and {len(problems) - limit} more")
    return lines


def draw_chart(layout: Layout, updated: datetime, output: Path) -> None:
    """Draw the layout as a PNG Gantt chart at ``output``.

    Parameters
    ----------
    layout : Layout
        What to draw.
    updated : datetime
        When the chart was made, shown in the subtitle.
    output : Path
        Where to write the PNG.
    """
    rows = max(layout.rows, 1)
    footer = footer_lines(layout.problems)
    bottom = (
        0.3 + 0.17 * len(footer) + 0.3
    )  # inches below the plot: problems, then the source line
    height = TOP + rows * ROW + bottom
    fig = Figure(figsize=(WIDTH, height), dpi=DPI, facecolor=SURFACE)
    ax = fig.add_axes(
        (LEFT / WIDTH, bottom / height, 1 - (LEFT + RIGHT) / WIDTH, rows * ROW / height)
    )
    ax.set_facecolor(SURFACE)
    x0, x1 = mdates.date2num(layout.first_day), mdates.date2num(layout.end)
    ax.set_xlim(x0, x1)
    ax.set_ylim(rows, 0)  # row 0 at the top
    ax.spines[:].set_visible(False)
    ax.set_yticks([])

    # Week lines at every Monday, labelled along the top.
    mondays = [
        layout.first_day + timedelta(weeks=i)
        for i in range((layout.end - layout.first_day).days // 7)
    ]
    week_x = mdates.date2num(mondays)
    for x in week_x:
        ax.axvline(x, color=GRIDLINE, linewidth=_pt(1), zorder=0)
    ax.xaxis.tick_top()
    ax.set_xticks(week_x, [f"{m.day} {m:%b}" for m in mondays])
    ax.tick_params(axis="x", length=0, pad=14, labelsize=8, labelcolor=INK_MUTED)

    # Lanes: the HPC name on the left, a divider between lanes, and a note in empty ones.
    names_x = ax.get_yaxis_transform()  # x in axes fraction, y in rows
    for i, lane in enumerate(layout.lanes):
        if i:
            ax.axhline(lane.top_row, color=DIVIDER, linewidth=_pt(1), zorder=1)
        ax.text(
            -0.012,
            lane.top_row + 0.5,
            lane.hpc,
            transform=names_x,
            ha="right",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=INK,
        )
        if lane.empty:
            ax.text(
                x0 + 0.5,
                lane.top_row + 0.5,
                "nothing planned",
                ha="left",
                va="center",
                fontsize=9,
                style="italic",
                color=INK_MUTED,
                **OVER_PLOT_TEXT,
            )
    if not layout.lanes:
        ax.text(
            0.5,
            0.5,
            "No HPCs listed yet. Add them to the HPCs tab of the sheet.",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=11,
            color=INK_SECONDARY,
            **OVER_PLOT_TEXT,
        )

    # Bars: thin, with 4 px rounded ends. A run reaching past the chart is drawn whole and clipped by the plot,
    # which squares off its cut ends.
    x_per_px = (x1 - x0) / ax.bbox.width
    y_per_px = rows / ax.bbox.height
    for bar in layout.bars:
        left, right = mdates.date2num(bar.start), mdates.date2num(bar.end)
        ax.add_patch(
            FancyBboxPatch(
                (left, bar.row + 0.62),
                right - left,
                10 * y_per_px,
                boxstyle=f"round,pad=0,rounding_size={4 * x_per_px}",
                mutation_aspect=y_per_px / x_per_px,
                facecolor=FINISHED if bar.finished else CURRENT,
                edgecolor="none",
                linewidth=0,
                zorder=2,
            )
        )
        ax.text(
            mdates.date2num(bar.label_x),
            bar.row + 0.55,
            bar.caption,
            ha=bar.label_align,
            va="bottom",
            fontsize=9,
            color=INK,
            **OVER_PLOT_TEXT,
        )

    # Today: a line at the start of today, so every finished bar ends at or before it.
    today = mdates.date2num(layout.today)
    ax.axvline(
        today, color=INK, linewidth=_pt(1.5), zorder=3
    )  # over the bars, under the text
    ax.text(
        today, 0, " today", ha="left", va="bottom", fontsize=8, color=INK, clip_on=False
    )

    # Title, subtitle and legend.
    margin = 0.25 / WIDTH
    fig.text(
        margin,
        1 - 0.22 / height,
        "HPC usage plan",
        ha="left",
        va="top",
        fontsize=16,
        color=INK,
    )
    fig.text(
        margin,
        1 - 0.6 / height,
        chart_subtitle(layout.first_day, layout.end, updated),
        ha="left",
        va="top",
        fontsize=10,
        color=INK_SECONDARY,
    )
    fig.legend(
        handles=[
            Patch(facecolor=CURRENT, edgecolor="none", label="underway or upcoming"),
            Patch(facecolor=FINISHED, edgecolor="none", label="finished"),
        ],
        loc="upper right",
        bbox_to_anchor=(1 - RIGHT / WIDTH, 1 - 0.2 / height),
        ncols=2,
        frameon=False,
        fontsize=9,
        labelcolor=INK_SECONDARY,
        handlelength=1.2,
        handleheight=0.8,
    )

    # Footer: problems in the sheet, then where the data comes from.
    if footer:
        fig.text(
            margin,
            (bottom - 0.25) / height,
            "\n".join(footer),
            ha="left",
            va="top",
            fontsize=8,
            color=INK_SECONDARY,
            linespacing=1.5,
        )
    fig.text(
        margin,
        0.12 / height,
        "Source: the HPC usage plan Google Sheet",
        ha="left",
        va="bottom",
        fontsize=8,
        color=INK_MUTED,
    )

    fig.savefig(output, dpi=DPI, facecolor=SURFACE)


# ---------------------------------------------------------------- upload


class UploadError(Exception):
    """The chart couldn't be uploaded with rclone."""


def rclone_upload(
    local: Path,
    destination: str,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    """Copy ``local`` to ``destination``, an rclone path such as ``dropbox:/QuakeCoRE/hpc_usage_gantt.png``.

    Parameters
    ----------
    local : Path
        The file to upload.
    destination : str
        The rclone path to write it to, replacing any file already there.
    run : callable, default subprocess.run
        Runs the rclone command; tests pass a fake.

    Raises
    ------
    UploadError
        If rclone is missing, times out or fails.
    """
    try:
        result = run(
            ["rclone", "copyto", str(local), destination],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError as exc:
        raise UploadError("rclone isn't installed (or isn't on PATH)") from exc
    except subprocess.TimeoutExpired as exc:
        raise UploadError(
            f"rclone timed out after {exc.timeout / 60:g} minutes"
        ) from exc
    if result.returncode != 0:
        errors = [line.strip() for line in result.stderr.splitlines() if line.strip()]
        raise UploadError(
            f"rclone failed: {errors[-1] if errors else f'exit code {result.returncode}'}"
        )


# ---------------------------------------------------------------- the command

DESTINATION = "dropbox:/QuakeCoRE/hpc_usage_gantt.png"
DEFAULT_OUTPUT = Path("hpc_usage_gantt.png")


def update_chart(
    sheet_id: str,
    today: date,
    now: datetime,
    upload_to: str | None,
    output: Path | None,
) -> int:
    """Download the sheet, draw the chart and, unless ``upload_to`` is None, upload it.

    Parameters
    ----------
    sheet_id : str
        The ID from the sheet's URL.
    today : date
        The day the chart is drawn for.
    now : datetime
        When the chart is made, shown in the subtitle.
    upload_to : str or None
        The rclone path to upload to, or None to only draw the chart.
    output : Path or None
        Where to write the PNG. None means ``hpc_usage_gantt.png`` when only drawing, otherwise a temporary file.

    Returns
    -------
    int
        The exit code: 0 on success, 1 if the sheet couldn't be read or the upload failed.
    """
    try:
        tabs = read_workbook(download_workbook(sheet_id))
    except SheetError as error:
        print(f"Couldn't read the planning sheet: {error}", file=sys.stderr)
        return 1
    first_day, _ = chart_window(today)
    schedule = parse_schedule(tabs, first_day)
    if schedule.problems:
        count = len(schedule.problems)
        print(
            f"The sheet has {count} problem{'' if count == 1 else 's'}, listed at the bottom of the chart.",
            file=sys.stderr,
        )
    layout = layout_chart(schedule, today)
    if upload_to is None:
        path = output or DEFAULT_OUTPUT
        draw_chart(layout, now, path)
        print(f"Wrote {path}")
        return 0
    with tempfile.TemporaryDirectory() as scratch:
        path = output or Path(scratch) / DEFAULT_OUTPUT.name
        draw_chart(layout, now, path)
        try:
            rclone_upload(path, upload_to)
        except UploadError as error:
            print(error, file=sys.stderr)
            return 1
    print(f"Uploaded to {upload_to}")
    return 0


app = App(help="Draw the HPC usage plan as a Gantt chart and upload it to Dropbox.")


@app.default
def main(
    *,
    upload: bool = True,
    output: Path | None = None,
    upload_to: str = DESTINATION,
    pretend_today_is: date | None = None,
) -> int:
    """Draw the chart from the sheet whose ID is in $SHEET_ID, and upload it.

    Parameters
    ----------
    upload : bool, default True
        Upload the chart. With --no-upload it is only drawn, into --output.
    output : Path or None, optional
        Where to write the PNG. Default: hpc_usage_gantt.png with --no-upload, otherwise a temporary file.
    upload_to : str, default DESTINATION
        The rclone destination to upload to.
    pretend_today_is : date or None, optional
        Draw the chart as if today were this date (YYYY-MM-DD), for testing.

    Returns
    -------
    int
        The exit code.
    """
    sheet_id = os.environ.get("SHEET_ID")
    if not sheet_id:
        print("SHEET_ID isn't set", file=sys.stderr)
        return 1
    now = datetime.now(NZ)
    today = pretend_today_is or now.date()
    return update_chart(sheet_id, today, now, upload_to if upload else None, output)


if __name__ == "__main__":
    app()
