# HPC Usage Gantt Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Slack bot with `hpc_gantt.py`, which downloads the "HPC usage plan" sheet, draws a Gantt chart PNG, and uploads it with rclone to `dropbox:/QuakeCoRE/hpc_usage_gantt.png`. Prove it on the laptop first, then run it weekly on GitHub Actions. *(Changed 2026-10-22: Tasks 9–10 replace Task 8's mantle deployment.)*

**Architecture:**
- **One file:** a single script, `hpc_gantt.py`. Since Task 11 it sits in a small uv project.
- **Reused:** the existing sheet download and checks.
- **New pure function:** `layout_chart` turns the checked sheet into lanes, rows, bars and captions. It's unit-tested.
- **New thin edges:** `draw_chart` draws that layout with matplotlib, and `upload` shells out to `rclone copyto`.
- **On GitHub Actions:** a scheduled workflow runs the script once a week, and on demand.

**Tech Stack:** Python 3.14, uv (a PEP 723 script until Task 11, then a uv project), openpyxl, requests, matplotlib (Agg), cyclopts 5, rclone, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-20-hpc-usage-gantt-design.md`. Read it first. It replaces the 2026-10-19 Slack-bot spec, which isn't kept in the repo.

## Global Constraints

- **The script:**
  - Requires Python `>=3.14`.
  - All code lives in `hpc_gantt.py`, renamed from `hpc_reminder.py` with `git mv`.
  - It's a uv script whose PEP 723 header lists exactly `cyclopts`, `matplotlib`, `openpyxl` and `requests`. matplotlib is added in Task 3. *(Since Task 11, `pyproject.toml` lists them instead.)*
  - Follow the style of `gantt.py`: a cyclopts `App` and numpy-style docstrings.
- **Test command (`TEST`):** `uv run --no-project --python 3.14 --with pytest --with-requirements hpc_gantt.py python -m pytest -q`. Single tests take the same command plus `tests/<file>::<test> -v`. *(Since Task 11: `uv run pytest -q`.)*
- **Tests stay offline:** no network calls, and they never run the real rclone. Fakes are monkeypatched onto `hpc_gantt`.
- **Dates and times:** all dates are `Pacific/Auckland`, and end dates are inclusive. A run is **finished** when its end date is before today.
- **Chart span:** from `first_day = week_monday(today) - 14 days` up to, but not including, `end = week_monday(today) + 91 days`. That's 15 weeks.
- **Defaults:**
  - Upload destination: `dropbox:/QuakeCoRE/hpc_usage_gantt.png`.
  - Local output: `hpc_usage_gantt.png`.
  - The sheet ID comes from the environment variable `SHEET_ID`.
- **Colours, from the dataviz reference palette:**

  | Use | Colour |
  |---|---|
  | Runs underway or upcoming | `#2a78d6` |
  | Finished runs | `#c3c2b7` |
  | Background | `#fcfcfb` |
  | Primary text | `#0b0b0b` |
  | Secondary text | `#52514e` |
  | Muted text | `#898781` |
  | Week gridlines | `#e1e0d9` |
  | Lane dividers | `#c3c2b7` |

  Text is never drawn in a bar colour.
- **No Slack:** no Slack code or tokens anywhere.
- **Dropbox only with the user:** uploading to or making links in Dropbox happens only in Tasks 7 and 10.

## Review Focus

1. **An empty or new sheet:** no HPCs and no runs, which is the real sheet today. Expect a chart that says nothing is listed yet, not a crash (Task 3).
2. **Long text or a run near the right edge.** Expect the caption shortened with "…" and kept inside the chart (Task 2).
3. **A run longer than the whole chart span.** Expect a full-width bar, cut square at both ends, with its caption still visible (Task 2).
4. **rclone missing or failing:** a new mantle account without rclone, or an expired token. Expect a clear error that names rclone, exit code 1, and no upload (Tasks 4–5).
5. **Many runs or many lanes.** Expect the image to grow taller rather than captions overlapping (Task 3).

---

## File Structure

| File | Responsibility |
|---|---|
| `hpc_gantt.py` | Sections: dates · the sheet (download, read, check) · chart layout · drawing · upload · the command |
| `tests/helpers.py` | `MON`, `EXAMPLE_TABS` (tidied sheet), `make_xlsx`, `with_runs`, `FakeResponse` |
| `tests/conftest.py` | The `example_schedule` fixture |
| `tests/test_dates.py`, `test_sheet.py`, `test_download.py`, `test_layout.py`, `test_draw.py`, `test_upload.py`, `test_cli.py` | One file per area |
| `tests/fixtures/google_export.xlsx` | Unchanged. It's the real export with the old Slack-era columns, which proves extra columns are ignored |
| `.github/workflows/update-chart.yml` | The weekly workflow (Task 10). It replaces the systemd units in `deploy/`, which Task 10 deletes |
| `README.md` | Rewritten for the chart |

---

### Task 1: Strip the Slack bot down to the sheet reader

**Files:**
- Rename: `hpc_reminder.py` → `hpc_gantt.py`; `tests/test_http.py` → `tests/test_download.py`
- Delete:
  - `tests/test_selection.py`, `tests/test_messages.py`, `tests/test_cli.py`
  - `deploy/hpc-reminder@.service`, `deploy/hpc-reminder-weekly.timer`, `deploy/hpc-reminder-heads-up.timer`, `deploy/hpc-reminder.env.example`
- Modify: `hpc_gantt.py`, `tests/helpers.py`, `tests/conftest.py`, `tests/test_sheet.py`, `tests/test_dates.py`, `tests/test_download.py`

**Interfaces:**
- Produces, replacing the old model:

```python
TABS = {"Runs": ["Person", "Description", "HPC", "Start date", "End date"], "People": ["Name"], "HPCs": ["HPC"]}

@dataclass(frozen=True)
class Run:
    row: int; person: str; description: str; hpc: str; start: date; end: date   # person/hpc: names as written on People/HPCs

@dataclass(frozen=True)
class Schedule:
    people: list[str]; hpcs: list[str]; runs: list[Run]; problems: list[str]    # people/hpcs in tab order

def parse_schedule(tabs: Mapping[str, Sequence[Sequence[object]]], first_day: date) -> Schedule
```

- Kept unchanged: `NZ`, `week_monday`, `format_date_range`, `nz_today`, `SheetError`, `read_workbook`, `download_workbook` and its retry helpers (`_Transient`, `_checked`, `with_retries`).
- Deleted:
  - `format_week`, `MEMBER_ID`, `Person`, `Hpc`, `Schedule.admins`;
  - the run-selection functions and all message formatting;
  - `SlackError`, `post_message`;
  - config, state and the commands, together with `app`, which comes back in Task 5.
  - Drop any imports that become unused.

**The problem lines change.** No line ends in a full stop, and none carries ", so it was skipped". The person reason becomes `"Jamie" isn't on the People tab`. Duplicates read `People row 3: "alex" is listed twice` or `HPCs row 3: "MAHUIKA" is listed twice`. The member-ID and no-admin checks go away. Structure problems read `The sheet has no "HPCs" tab` and `The Runs tab has no "End date" column`. All other rules stay as they are now, including the order the problems are listed in.

**When rows are checked:**
- A row whose end date is before `first_day` is skipped without checking, unless its start date is after its end date.
- Unreadable dates are always reported.

- [ ] **Step 1: Restructure the files.**
  - Run `git mv hpc_reminder.py hpc_gantt.py` and `git mv tests/test_http.py tests/test_download.py`.
  - `git rm` the three test files and four deploy files listed above.
  - Change the module docstring to `"""Draw the team's HPC usage plan as a Gantt chart and upload it to Dropbox."""`.
  - In `test_download.py`, keep only the five `download_workbook` tests, and import from `hpc_gantt`.

- [ ] **Step 2: Rewrite the sheet tests for the new behaviour.**
  - **`tests/helpers.py`:** `EXAMPLE_TABS["People"]` becomes `[["Name"], ["Alex"], ["Sam"], ["Jordan"], ["Riley"], ["Casey"], ["Morgan"]]`, and `EXAMPLE_TABS["HPCs"]` becomes `[["HPC"], ["Mahuika"], ["Frontera"], ["Setonix"], ["Test cluster"]]`. Delete `LINK` and `EXPECTED_*`. Keep `MON`, `make_xlsx`, `with_runs` and `FakeResponse`.
  - **`tests/conftest.py`:** import from `hpc_gantt`.
  - **`tests/test_dates.py`:** drop the `format_week` test, and import from `hpc_gantt`.
  - **`tests/test_sheet.py`:**
    - Import `Run, SheetError, parse_schedule, read_workbook` from `hpc_gantt`.
    - Keep the two `read_workbook` tests and `test_blank_rows_are_ignored`. In the latter, append `[None]` rows to People and HPCs, since each tab now has one column.
    - Replace the other tests with these:

```python
def test_parse_example(example_schedule):
    s = example_schedule
    assert [r.row for r in s.runs] == [2, 3, 4, 5]
    assert s.runs[0] == Run(
        2,
        "Alex",
        "Hikurangi rupture scenarios",
        "Mahuika",
        date(2026, 10, 12),
        date(2026, 11, 1),
    )
    assert s.people == ["Alex", "Sam", "Jordan", "Riley", "Casey", "Morgan"]
    assert s.hpcs == ["Mahuika", "Frontera", "Setonix", "Test cluster"]
    assert s.problems == [
        'Row 6 (Casey, Frontera): start date "early Nov" isn\'t a date'
    ]


def test_names_match_ignoring_case_and_spaces():
    run = parse_schedule(with_runs([" alex ", None, "mahuika ", d1, d2]), MON).runs[0]
    assert (run.person, run.hpc, run.description) == ("Alex", "Mahuika", "")


def test_extra_columns_and_tab_spelling_are_ignored():
    tabs = {
        "runs": [["Person", "Description", "HPC", "Start date", "End date"]],
        "people": [
            ["Slack member ID", " NAME ", "Admin"],
            ["U04ABC1DEF", "Alex", True],
        ],
        "HPCs": [["Alert if idle", "HPC"], [True, "Mahuika"]],
    }
    s = parse_schedule(tabs, MON)
    assert (s.people, s.hpcs, s.problems) == (["Alex"], ["Mahuika"], [])


@pytest.mark.parametrize(
    "row, problem",
    [
        (
            ["Jamie", "x", "Mahuika", d1, d2],
            'Row 2 (Jamie, Mahuika): "Jamie" isn\'t on the People tab',
        ),
        (
            ["Alex", "x", "Kupe", d1, d2],
            'Row 2 (Alex, Kupe): HPC "Kupe" isn\'t on the HPCs tab',
        ),
        ([None, "x", "Mahuika", d1, d2], "Row 2 (?, Mahuika): no person given"),
        (
            ["Alex", "x", "Mahuika", d2, d1],
            "Row 2 (Alex, Mahuika): start date is after the end date",
        ),
        (
            ["Alex", "x", "Mahuika", d1, None],
            "Row 2 (Alex, Mahuika): end date is empty",
        ),
        (
            ["Jamie", "x", "Kupe", d1, d2],
            'Row 2 (Jamie, Kupe): "Jamie" isn\'t on the People tab; HPC "Kupe" isn\'t on the HPCs tab',
        ),
    ],
)
def test_bad_rows_are_reported_and_skipped(row, problem):
    s = parse_schedule(with_runs(row), MON)
    assert (s.runs, s.problems) == ([], [problem])


def test_rows_that_ended_before_the_first_day_are_not_checked():
    s = parse_schedule(
        with_runs(["Jamie", "x", "Kupe", "early Oct", D(2026, 10, 18)]), MON
    )
    assert (s.runs, s.problems) == ([], [])


def test_unreadable_end_date_is_always_reported():
    s = parse_schedule(
        with_runs(["Alex", "x", "Mahuika", D(2026, 10, 1), "whenever"]), MON
    )
    assert s.problems == ['Row 2 (Alex, Mahuika): end date "whenever" isn\'t a date']


def test_reversed_dates_are_reported_even_when_the_end_is_past():
    s = parse_schedule(
        with_runs(["Alex", "x", "Mahuika", D(2026, 12, 28), D(2026, 1, 8)]),
        date(2026, 12, 21),
    )
    assert (s.runs, s.problems) == (
        [],
        ["Row 2 (Alex, Mahuika): start date is after the end date"],
    )


def test_sheet_level_problems():
    tabs = {
        "People": [["Name"], ["Alex"], ["alex"]],
        "HPCs": [["HPC"], ["Mahuika"], ["MAHUIKA"]],
        "Runs": [["Person", "Description", "HPC", "Start date"]],
    }
    assert parse_schedule(tabs, MON).problems == [
        'The Runs tab has no "End date" column',
        'People row 3: "alex" is listed twice',
        'HPCs row 3: "MAHUIKA" is listed twice',
    ]
    assert (
        parse_schedule(
            {"Runs": EXAMPLE_TABS["Runs"], "People": EXAMPLE_TABS["People"]}, MON
        ).problems[0]
        == 'The sheet has no "HPCs" tab'
    )


def test_real_google_export():
    tabs = read_workbook(
        (Path(__file__).parent / "fixtures" / "google_export.xlsx").read_bytes()
    )
    s = parse_schedule(tabs, MON)
    assert (s.people, s.hpcs, s.runs) == ([], [], [])
    assert s.problems == ["Row 2 (?, ?): no person given; no HPC given"]
```

- [ ] **Step 3: Run `TEST`.** Expected: FAIL. `Run` takes a `Person` object, `format_week` is still exported, and the problem wording is the old wording.
- [ ] **Step 4: Simplify `hpc_gantt.py`.** Change the model and `parse_schedule` as described in Interfaces, and delete the listed code.
- [ ] **Step 5: Run `TEST`.** Expected: all pass, with nothing collected from the deleted test files.
- [ ] **Step 6: Commit**

```bash
git add -A hpc_gantt.py tests deploy
git commit -m "refactor: strip the Slack bot down to the sheet reader" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Chart layout

**Files:**
- Modify: `hpc_gantt.py`
- Create: `tests/test_layout.py`

**Interfaces:**
- Consumes: `Schedule`, `Run` and `week_monday` from Task 1.
- Produces:

```python
@dataclass(frozen=True)
class Bar:
    row: int            # 0 = top row of the chart
    start: date         # first day drawn (run start, cut at first_day)
    end: date           # day after the last day drawn (run end + 1 day, cut at the chart end)
    cut_start: bool     # the run began before first_day
    cut_end: bool       # the run continues past the chart end
    finished: bool      # run.end < today
    caption: str        # from caption()
    label_x: date       # where the caption is anchored
    label_align: str    # "left" or "right"

@dataclass(frozen=True)
class Lane:
    hpc: str; top_row: int; rows: int; empty: bool   # an empty lane still has 1 row

@dataclass(frozen=True)
class Layout:
    first_day: date; end: date; today: date; lanes: list[Lane]; bars: list[Bar]; problems: list[str]
    @property
    def rows(self) -> int: ...   # total rows, 0 when there are no lanes

def chart_window(today: date) -> tuple[date, date]            # (first_day, end), end exclusive
def caption(person: str, description: str, max_chars: int = 60) -> str
def layout_chart(schedule: Schedule, today: date) -> Layout
```

**Rules:**
- **Which runs:** only runs with `start < end` and `run.end >= first_day`.
- **Lanes:** one per HPC, in `schedule.hpcs` order. Within a lane, each run gets its own row, sorted by `(start, person.casefold(), row)`. Rows are numbered from 0 at the top, continuing across lanes.
- **Captions:**
  - The text is `"{person} · {description}"`, or just the person when the description is empty.
  - Anything longer than `max_chars` is cut to `max_chars - 1` characters plus `…`.
  - The caption is anchored at `bar.start` and left-aligned, unless the bar starts at or after `first_day + 70 days` (the last third of the chart). Then it's anchored at `bar.end` and right-aligned, so it stays inside the chart.
- **Problems:** `problems` is passed through from the schedule.

- [ ] **Step 1: Write the failing tests** in `tests/test_layout.py`

```python
from datetime import date

from hpc_gantt import Run, Schedule, caption, chart_window, layout_chart

TUE = date(2026, 10, 20)


def test_chart_window():
    assert chart_window(TUE) == (date(2026, 10, 5), date(2027, 1, 18))
    assert chart_window(date(2026, 10, 25)) == (date(2026, 10, 5), date(2027, 1, 18))


def test_lanes_follow_the_hpcs_tab(example_schedule):
    lanes = layout_chart(example_schedule, TUE).lanes
    assert [(l.hpc, l.top_row, l.rows, l.empty) for l in lanes] == [
        ("Mahuika", 0, 2, False),
        ("Frontera", 2, 1, False),
        ("Setonix", 3, 1, False),
        ("Test cluster", 4, 1, True),
    ]


def test_bars(example_schedule):
    layout = layout_chart(example_schedule, TUE)
    assert layout.rows == 5 and layout.problems == example_schedule.problems
    assert [
        (
            b.row,
            b.start,
            b.end,
            b.cut_start,
            b.cut_end,
            b.finished,
            b.caption,
            b.label_x,
            b.label_align,
        )
        for b in layout.bars
    ] == [
        (
            0,
            date(2026, 10, 12),
            date(2026, 11, 2),
            False,
            False,
            False,
            "Alex · Hikurangi rupture scenarios",
            date(2026, 10, 12),
            "left",
        ),
        (
            1,
            date(2026, 10, 26),
            date(2026, 11, 14),
            False,
            False,
            False,
            "Jordan · Alpine Fault ensemble, part 2",
            date(2026, 10, 26),
            "left",
        ),
        (
            2,
            date(2026, 10, 19),
            date(2026, 10, 24),
            False,
            False,
            False,
            "Sam · Kaikōura validation runs",
            date(2026, 10, 19),
            "left",
        ),
        (
            3,
            date(2026, 10, 28),
            date(2026, 11, 7),
            False,
            False,
            False,
            "Riley · Velocity model sensitivity tests",
            date(2026, 10, 28),
            "left",
        ),
    ]


def test_finished_runs(example_schedule):
    bars = layout_chart(example_schedule, date(2026, 10, 26)).bars
    assert [(b.caption.split(" ·")[0], b.finished) for b in bars] == [
        ("Alex", False),
        ("Jordan", False),
        ("Sam", True),
        ("Riley", False),
    ]


def test_run_longer_than_the_chart_is_cut_at_both_ends():
    s = Schedule(
        ["Alex"],
        ["Mahuika"],
        [
            Run(
                2,
                "Alex",
                "Long campaign",
                "Mahuika",
                date(2026, 9, 1),
                date(2027, 3, 1),
            )
        ],
        [],
    )
    (bar,) = layout_chart(s, TUE).bars
    assert (
        bar.start,
        bar.end,
        bar.cut_start,
        bar.cut_end,
        bar.label_x,
        bar.label_align,
    ) == (date(2026, 10, 5), date(2027, 1, 18), True, True, date(2026, 10, 5), "left")


def test_runs_outside_the_chart_leave_the_lane_empty():
    runs = [
        Run(2, "Alex", "", "Mahuika", date(2026, 9, 1), date(2026, 10, 4)),
        Run(3, "Alex", "", "Mahuika", date(2027, 1, 18), date(2027, 1, 20)),
    ]
    layout = layout_chart(Schedule(["Alex"], ["Mahuika"], runs, []), TUE)
    assert layout.bars == [] and layout.lanes[0].empty and layout.rows == 1


def test_late_starting_run_gets_a_right_aligned_caption():
    s = Schedule(
        ["Alex"],
        ["Mahuika"],
        [Run(2, "Alex", "", "Mahuika", date(2026, 12, 20), date(2026, 12, 24))],
        [],
    )
    (bar,) = layout_chart(s, TUE).bars
    assert (bar.label_x, bar.label_align) == (date(2026, 12, 25), "right")


def test_caption():
    assert caption("Alex", "Short") == "Alex · Short"
    assert caption("Alex", "") == "Alex"
    long = caption("Alex", "x" * 100)
    assert len(long) == 60 and long.endswith("…")


def test_no_hpcs_means_no_rows():
    assert layout_chart(Schedule([], [], [], []), TUE).rows == 0
```

- [ ] **Step 2: Run `TEST tests/test_layout.py`.** Expected: FAIL with `ImportError`.
- [ ] **Step 3: Implement** `Bar`, `Lane`, `Layout`, `chart_window`, `caption` and `layout_chart`.
- [ ] **Step 4: Run the full `TEST`.** Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add hpc_gantt.py tests/test_layout.py
git commit -m "feat: lay out runs as Gantt chart lanes, rows and captions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Drawing the chart

Before writing any chart code, load the `dataviz` skill. Its mark specs and anti-patterns apply.

**Files:**
- Modify: `hpc_gantt.py`, adding `matplotlib` to the PEP 723 header
- Create: `tests/test_draw.py`

**Interfaces:**
- Consumes: `Layout`, `Bar`, `Lane` from Task 2, and `format_date_range` and `NZ` from Task 1.
- Produces:
  - `chart_subtitle(first_day: date, end: date, updated: datetime) -> str`
  - `footer_lines(problems: list[str], limit: int = 8) -> list[str]`
  - `draw_chart(layout: Layout, updated: datetime, output: Path) -> None`

**Drawing rules:**
- **Backend:** call `matplotlib.use("Agg")` before importing pyplot.
- **Size:** 14 in wide at 120 dpi, which is 1680 px. The height grows with the number of rows: 0.42 in per row (at least one), plus room for the title, axis and footer.
- **Background:** `#fcfcfb` everywhere. No axes box.
- **Week lines:** a 1 px solid line at every Monday of the chart, coloured `#e1e0d9`. Each is labelled at the top, like `19 Oct`, in muted text.
- **Lanes:**
  - The HPC name sits at the left of the lane's top row, in bold primary text.
  - A 1 px divider (`#c3c2b7`) runs between lanes.
  - An empty lane shows "nothing planned" in muted italics.
- **Bars:**
  - The fill is `#2a78d6`, or `#c3c2b7` when finished. No outline.
  - Each bar is about 10 px tall and sits in the lower part of its row.
  - Ends are rounded by 4 px, using `FancyBboxPatch` with a `mutation_aspect` that keeps the corners round.
  - At a cut end, extend the patch a little past the chart edge so the axes clipping squares that end off.
- **Captions:** 9 pt primary text, just above the bar, at `label_x` with `label_align`.
- **Today:** a 1.5 px solid vertical line in primary text colour, with "today" written above the top row.
- **Legend:** top right. Two swatches: "underway or upcoming" (blue) and "finished" (grey), with the text in secondary colour.
- **Title and subtitle:** the title is "HPC usage plan" (16 pt, primary). The subtitle is `chart_subtitle(...)` (10 pt, secondary).
- **Footer:** `footer_lines(...)` in 8 pt secondary text, then always "Source: the HPC usage plan Google Sheet" in muted text.
- **No lanes at all:** keep the week lines and the today line, and write "No HPCs listed yet. Add them to the HPCs tab of the sheet." in secondary text.
- **Saving:** `fig.savefig(output, dpi=120, facecolor="#fcfcfb")`, then `plt.close(fig)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_draw.py`

```python
import struct
import warnings
from datetime import date, datetime

from hpc_gantt import (
    NZ,
    Run,
    Schedule,
    chart_subtitle,
    draw_chart,
    footer_lines,
    layout_chart,
)

UPDATED = datetime(2026, 10, 20, 14, 0, tzinfo=NZ)
TUE = date(2026, 10, 20)


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_chart_subtitle():
    assert chart_subtitle(date(2026, 10, 5), date(2027, 1, 18), UPDATED) == (
        "Updated Tue 20 Oct 2026, 14:00 NZDT · showing 5 Oct 2026 – 17 Jan 2027"
    )


def test_footer_lines():
    assert footer_lines([]) == []
    assert footer_lines(["a"]) == ["Problems in the sheet:", "a"]
    assert footer_lines([f"p{i}" for i in range(10)]) == [
        "Problems in the sheet:",
        *[f"p{i}" for i in range(8)],
        "…and 2 more",
    ]


def test_draws_a_png(example_schedule, tmp_path):
    draw_chart(layout_chart(example_schedule, TUE), UPDATED, tmp_path / "chart.png")
    assert png_size(tmp_path / "chart.png")[0] == 1680


def test_height_grows_with_rows(example_schedule, tmp_path):
    many = [
        Run(i, "Alex", f"run {i}", "Mahuika", date(2026, 10, 20), date(2026, 10, 30))
        for i in range(2, 32)
    ]
    draw_chart(layout_chart(example_schedule, TUE), UPDATED, tmp_path / "few.png")
    draw_chart(
        layout_chart(Schedule(["Alex"], ["Mahuika"], many, []), TUE),
        UPDATED,
        tmp_path / "many.png",
    )
    assert png_size(tmp_path / "many.png")[1] > png_size(tmp_path / "few.png")[1]


def test_empty_sheet_still_draws(tmp_path):
    draw_chart(
        layout_chart(Schedule([], [], [], []), TUE), UPDATED, tmp_path / "empty.png"
    )
    assert png_size(tmp_path / "empty.png")[0] == 1680


def test_unicode_and_long_text_draw_without_warnings(tmp_path):
    s = Schedule(
        ["Ōtautahi Ngā"],
        ["Mahuika"],
        [
            Run(
                2,
                "Ōtautahi Ngā",
                "Kaikōura " * 30,
                "Mahuika",
                date(2026, 9, 1),
                date(2027, 3, 1),
            )
        ],
        [f"Row {i} (?, ?): no person given" for i in range(12)],
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        draw_chart(layout_chart(s, TUE), UPDATED, tmp_path / "text.png")
```

- [ ] **Step 2: Run `TEST tests/test_draw.py`.** Expected: FAIL with `ImportError`.
- [ ] **Step 3: Implement** `chart_subtitle`, `footer_lines` and `draw_chart`, and add `matplotlib` to the script header.
- [ ] **Step 4: Run the full `TEST`.** Expected: all pass, with no warnings in the output.
- [ ] **Step 5: Look at the charts.** Render the example chart (dated `TUE`) and the empty chart into the session scratchpad, then open both PNGs and look at them.
  - Check for overlapping captions, clipped text, bars sitting wrongly against the week lines, and a legend that hides data.
  - Check that cut ends are square and the other ends are round.
  - Check that the chart matches the anti-patterns list of the `dataviz` skill.

  Fix anything wrong and look again. Expected: a clean chart. Write down in the ledger what you checked.
- [ ] **Step 6: Commit**

```bash
git add hpc_gantt.py tests/test_draw.py
git commit -m "feat: draw the Gantt chart with matplotlib" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Upload with rclone

**Files:**
- Modify: `hpc_gantt.py`
- Create: `tests/test_upload.py`

**Interfaces:**
- Produces:
  - `class UploadError(Exception)`
  - `upload(local: Path, destination: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None`

**Behaviour:**
- **The call:** `run(["rclone", "copyto", str(local), destination], capture_output=True, text=True, timeout=300)`.
- **rclone not found:** `FileNotFoundError` → `UploadError("rclone isn't installed (or isn't on PATH)")`.
- **Timeout:** `subprocess.TimeoutExpired` → `UploadError("rclone timed out after 5 minutes")`.
- **Failure:** a non-zero exit → `UploadError(f"rclone failed: {last non-empty stderr line}")`.

- [ ] **Step 1: Write the failing tests** in `tests/test_upload.py`

```python
import subprocess
from pathlib import Path

import pytest

from hpc_gantt import UploadError, upload

DEST = "dropbox:/QuakeCoRE/hpc_usage_gantt.png"


def test_upload_runs_rclone_copyto():
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    upload(Path("/tmp/chart.png"), DEST, run=run)
    assert calls == [
        (
            ["rclone", "copyto", "/tmp/chart.png", DEST],
            {"capture_output": True, "text": True, "timeout": 300},
        )
    ]


def test_missing_rclone_is_explained():
    def run(args, **kwargs):
        raise FileNotFoundError("rclone")

    with pytest.raises(UploadError, match="rclone isn't installed"):
        upload(Path("/tmp/chart.png"), DEST, run=run)


def test_rclone_failure_shows_its_last_error_line():
    def run(args, **kwargs):
        return subprocess.CompletedProcess(
            args, 1, "", "2026/10/20 NOTICE: x\n2026/10/20 ERROR : token expired\n\n"
        )

    with pytest.raises(
        UploadError, match="rclone failed: 2026/10/20 ERROR : token expired$"
    ):
        upload(Path("/tmp/chart.png"), DEST, run=run)


def test_rclone_timeout_is_explained():
    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 300)

    with pytest.raises(UploadError, match="timed out"):
        upload(Path("/tmp/chart.png"), DEST, run=run)
```

- [ ] **Step 2: Run `TEST tests/test_upload.py`.** Expected: FAIL with `ImportError`.
- [ ] **Step 3: Implement** `UploadError` and `upload`.
- [ ] **Step 4: Run the full `TEST`.** Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add hpc_gantt.py tests/test_upload.py
git commit -m "feat: upload the chart with rclone" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The command

**Files:**
- Modify: `hpc_gantt.py`, `.gitignore` (add `hpc_usage_gantt.png`)
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: all of the above. Call `download_workbook`, `draw_chart` and `upload` through their module-level names, so tests can patch them.
- Produces:

```python
DESTINATION = "dropbox:/QuakeCoRE/hpc_usage_gantt.png"
DEFAULT_OUTPUT = Path("hpc_usage_gantt.png")

def update_chart(sheet_id: str, today: date, now: datetime, upload_to: str | None, output: Path | None) -> int
app = App(help="Draw the HPC usage plan as a Gantt chart and upload it to Dropbox.")
@app.default
def main(*, upload: bool = True, output: Path | None = None, upload_to: str = DESTINATION,
         pretend_today_is: date | None = None) -> int
```

**Behaviour:**
- **`update_chart`:**
  1. Download, then call `read_workbook`. If either raises `SheetError`, print `Couldn't read the planning sheet: …` to stderr and return 1. Nothing is drawn or uploaded.
  2. Set `first_day, _ = chart_window(today)`, then call `parse_schedule(tabs, first_day)` and `layout_chart(schedule, today)`. Print each problem to stderr as `Sheet problem: …`.
  3. If `upload_to is None`:
     - draw to `output or DEFAULT_OUTPUT`;
     - print `Wrote <path>`;
     - return 0.
  4. Otherwise:
     - draw to `output`, or into a `tempfile.TemporaryDirectory()` when no output is given;
     - call `upload(path, upload_to)`;
     - on `UploadError`, print it to stderr and return 1;
     - on success, print `Uploaded to <upload_to>` and return 0.
- **`main`:**
  - If `SHEET_ID` is missing or empty, print `SHEET_ID isn't set` to stderr and return 1.
  - Set `now = datetime.now(NZ)` and `today = pretend_today_is or now.date()`.
  - Return `update_chart(sheet_id, today, now, upload_to if upload else None, output)`.
- **The flags:** cyclopts turns `upload: bool = True` into `--upload` and `--no-upload`, and `pretend_today_is` into `--pretend-today-is`.
- **Script end:** the script ends with `if __name__ == "__main__": app()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_cli.py`

```python
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import hpc_gantt
from helpers import EXAMPLE_TABS, make_xlsx
from hpc_gantt import DESTINATION, NZ, SheetError, UploadError, update_chart

NOW = datetime(2026, 10, 20, 14, 0, tzinfo=NZ)


@pytest.fixture
def world(monkeypatch):
    uploads = []
    monkeypatch.setattr(
        hpc_gantt, "download_workbook", lambda sheet_id: make_xlsx(EXAMPLE_TABS)
    )

    def fake_upload(local, destination):
        uploads.append((destination, local.read_bytes()[:4] == b"\x89PNG"))

    monkeypatch.setattr(hpc_gantt, "upload", fake_upload)
    return SimpleNamespace(uploads=uploads)


def test_no_upload_writes_the_chart(world, tmp_path):
    assert update_chart("ID", NOW.date(), NOW, None, tmp_path / "c.png") == 0
    assert (tmp_path / "c.png").read_bytes()[:4] == b"\x89PNG" and world.uploads == []


def test_upload_sends_a_fresh_png(world):
    assert update_chart("ID", NOW.date(), NOW, "dropbox:/test/x.png", None) == 0
    assert world.uploads == [("dropbox:/test/x.png", True)]


def test_unreadable_sheet_uploads_nothing(world, monkeypatch, capsys):
    def broken(sheet_id):
        raise SheetError("download failed with HTTP 404")

    monkeypatch.setattr(hpc_gantt, "download_workbook", broken)
    assert update_chart("ID", NOW.date(), NOW, DESTINATION, None) == 1
    assert world.uploads == [] and "HTTP 404" in capsys.readouterr().err


def test_upload_failure_exits_1(world, monkeypatch, capsys):
    def failing(local, destination):
        raise UploadError("rclone isn't installed (or isn't on PATH)")

    monkeypatch.setattr(hpc_gantt, "upload", failing)
    assert update_chart("ID", NOW.date(), NOW, DESTINATION, None) == 1
    assert "rclone isn't installed" in capsys.readouterr().err


def test_sheet_problems_go_to_stderr(world, tmp_path, capsys):
    update_chart("ID", NOW.date(), NOW, None, tmp_path / "c.png")
    assert (
        'Sheet problem: Row 6 (Casey, Frontera): start date "early Nov" isn\'t a date'
        in capsys.readouterr().err
    )


def test_cli_flags(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(
        hpc_gantt,
        "update_chart",
        lambda sheet_id, today, now, upload_to, output: (
            seen.append((sheet_id, today, upload_to, output)) or 0
        ),
    )
    monkeypatch.setenv("SHEET_ID", "abc")
    with pytest.raises(SystemExit) as no_upload:
        hpc_gantt.app(
            [
                "--no-upload",
                "--output",
                str(tmp_path / "c.png"),
                "--pretend-today-is",
                "2026-10-20",
            ]
        )
    with pytest.raises(SystemExit) as default:
        hpc_gantt.app([])
    assert (no_upload.value.code, default.value.code) == (0, 0)
    assert seen[0] == ("abc", date(2026, 10, 20), None, tmp_path / "c.png")
    assert seen[1][2:] == (DESTINATION, None)


def test_missing_sheet_id(monkeypatch):
    monkeypatch.delenv("SHEET_ID", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        hpc_gantt.app(["--no-upload"])
    assert exit_info.value.code == 1
```

- [ ] **Step 2: Run `TEST tests/test_cli.py`.** Expected: FAIL with `ImportError`.
- [ ] **Step 3: Implement** `DESTINATION`, `DEFAULT_OUTPUT`, `run`, `app` and `main`, and add `hpc_usage_gantt.png` to `.gitignore`.
- [ ] **Step 4: Run the full `TEST`.** Expected: all pass.
- [ ] **Step 5: Smoke test against the real sheet.** This draws only and uploads nothing:

```bash
SHEET_ID=<sheet ID> uv run --script hpc_gantt.py --no-upload --output <scratchpad>/real.png; echo "exit $?"
```

Expected: `Wrote …real.png`, then `exit 0`. Open the PNG and look at it. Until HPCs are listed, it should show the "No HPCs listed yet" message.

- [ ] **Step 6: Commit**

```bash
git add hpc_gantt.py tests/test_cli.py .gitignore
git commit -m "feat: add the hpc_gantt command" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: systemd units and README

**Files:**
- Create: `deploy/hpc-gantt.service`, `deploy/hpc-gantt.timer`
- Rewrite: `README.md`

- [ ] **Step 1: Write the units.** The `CHANGE_ME` values get filled in on mantle in Task 8.

`deploy/hpc-gantt.service`:

```ini
[Unit]
Description=Draw the HPC usage Gantt chart and upload it to Dropbox
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
# The account whose rclone config has the "dropbox" remote
User=CHANGE_ME
Environment=SHEET_ID=CHANGE_ME
# Full path to that account's uv (e.g. /home/<account>/.local/bin/uv)
ExecStart=CHANGE_ME/uv run --script /opt/hpc-gantt/hpc_gantt.py
```

`deploy/hpc-gantt.timer`:

```ini
[Unit]
Description=Refresh the HPC usage Gantt chart every hour

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 2: Check the schedule.** Run `systemd-analyze calendar hourly`. Expected: the next run is on the hour.

- [ ] **Step 2b: Pin the libraries** *(added 2026-10-20; the user chose this over Docker)*. Run `uv lock --script hpc_gantt.py` and commit `hpc_gantt.py.lock`. The README's deploy step copies it to mantle with the script.

- [ ] **Step 3: Rewrite `README.md`** with these sections:
  1. **What it does:** the chart, the fixed Dropbox file, and the Slack reminder, which is set up outside the code. Link to the spec.
  2. **The sheet:** the three tabs and their columns.
  3. **Try it on your laptop:**
     - `SHEET_ID=… uv run --script hpc_gantt.py --no-upload` writes `hpc_usage_gantt.png`;
     - `--upload-to dropbox:/QuakeCoRE/<you>/hpc_usage_gantt_test.png` tries an upload.
  4. **Tests:** the `TEST` command.
  5. **The share link and the Slack reminder:**
     - `rclone link dropbox:/QuakeCoRE/hpc_usage_gantt.png` creates the link;
     - `/remind #channel "HPC usage plan: <link>" every Monday at 9am` sets up the reminder.
  6. **Deploy on mantle:**
     1. Pick an account with rclone set up. On a new account, install rclone and uv, then copy in an `rclone.conf` with the `dropbox` remote. It must be owned by that account, with mode 600, and stay writable because rclone refreshes the token. Optionally, give the bot its own token (`rclone authorize "dropbox"`), so it can be revoked without affecting anyone else.
     2. Copy `hpc_gantt.py` to `/opt/hpc-gantt/`.
     3. Fill in the `CHANGE_ME` values and install both units into `/etc/systemd/system/`.
     4. Run `sudo systemctl daemon-reload`.
     5. Test with `sudo systemctl start hpc-gantt.service && journalctl -u hpc-gantt -n 20`.
     6. Run `sudo systemctl enable --now hpc-gantt.timer`.
  7. **Operating:**
     - `systemctl list-timers hpc-gantt.timer` shows the next run;
     - `journalctl -u hpc-gantt` shows the log;
     - `sudo systemctl start hpc-gantt.service` refreshes the chart now.

- [ ] **Step 4: Commit**

```bash
git add deploy README.md
git commit -m "feat: add the hourly systemd timer and rewrite the README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Laptop trial in Dropbox (with the user)

These steps write to the team's Dropbox. Steps 3 and 5 publish a link, so stop before each one for the user's explicit go-ahead.

- [ ] **Step 1: Upload to a test file in the user's own folder.**

```bash
SHEET_ID=<sheet ID> uv run --script hpc_gantt.py \
  --upload-to dropbox:/QuakeCoRE/<you>/hpc_usage_gantt_test.png --output <scratchpad>/first.png
rclone lsf dropbox:/QuakeCoRE/<you>/ | grep hpc_usage_gantt_test.png
```

Expected: `Uploaded to dropbox:/QuakeCoRE/<you>/hpc_usage_gantt_test.png`, and the file is listed.

- [ ] **Step 2: Upload again with different content.** Repeat Step 1 with `--pretend-today-is 2026-11-02` and `--output <scratchpad>/second.png`. Expected: success, with the same file name.
- [ ] **Step 3: Check the share link, after the user's go-ahead.**

```bash
rclone link dropbox:/QuakeCoRE/<you>/hpc_usage_gantt_test.png
```

Note the URL. Then download it with `curl -sL "<url with dl=1>" -o <scratchpad>/via_link.png` and compare `sha256sum` against `second.png`.
- [ ] **Step 4: Check the link survives a re-upload.** Upload once more (Step 1, with `--output <scratchpad>/third.png`). Run `rclone link` again: expect the same URL. Download it again: expect it to match `third.png`. If the URL changes, or the download shows the old chart, stop and tell the user. The design's assumption that the link stays put would then be wrong.
- [ ] **Step 5: The real upload, when the user says so.** Run without `--upload-to`, which uses the default `dropbox:/QuakeCoRE/hpc_usage_gantt.png`. Then, with the user's go-ahead, run `rclone link` on that path and give the URL to the user for their Slack `/remind`.

Record the outcome of each step in the ledger.

---

### Task 8: Go live on mantle (with the user)

*Superseded on 2026-10-22: the bot runs on GitHub Actions instead (Tasks 9–10). Nothing was set up on mantle.*

This needs the user: mantle access (they run the commands, or set up SSH for Claude), and a decision on which account runs the service.

- [ ] **Step 1: Check prerequisites with the user.**
  - Choose the account.
  - Check whether rclone and uv are installed for it.
  - Check that mantle's C library is new enough: `ldd --version` must show glibc 2.28 or later, which the locked matplotlib and numpy wheels need *(final review)*.
  - Check that the account has a real home directory, where uv's cache, the downloaded Python, matplotlib's cache and the rclone config live *(final review)*.
  - Make sure its `rclone.conf` has a working `dropbox` remote: `rclone lsf dropbox:/QuakeCoRE --max-depth 1` should run as that account without errors.
- [ ] **Step 2: Follow the README's "Deploy on mantle" steps 1–4.** Then run the service once: `sudo systemctl start hpc-gantt.service`. Expected: `journalctl -u hpc-gantt -n 20` shows `Uploaded to dropbox:/QuakeCoRE/hpc_usage_gantt.png`, and the file's time changes (`rclone lsl dropbox:/QuakeCoRE/hpc_usage_gantt.png`).
- [ ] **Step 3: Enable the timer.** `sudo systemctl enable --now hpc-gantt.timer`. Expected: `systemctl list-timers hpc-gantt.timer` shows the next run on the hour.
- [ ] **Step 4: Check it ran on its own.** An hour later, `journalctl -u hpc-gantt --since -1h` shows a successful run.

---

### Task 9: Log only the number of sheet problems

On GitHub, the log of every run is public, and today each problem is logged with names and cell text, e.g. `Sheet problem: Row 6 (Casey, Frontera): start date "early Nov" isn't a date`. Log only the count instead. The chart's footer already lists the problems.

**Files:** `hpc_gantt.py` (`update_chart`), `tests/test_cli.py`.

- [ ] **Step 1: Replace the test.** In `tests/test_cli.py`, replace `test_sheet_problems_go_to_stderr` with the test below, and import `with_runs` from `helpers`:

```python
@pytest.mark.parametrize(
    "problem_rows, logged",
    [
        (0, ""),
        (1, "The sheet has 1 problem, listed at the bottom of the chart.\n"),
        (2, "The sheet has 2 problems, listed at the bottom of the chart.\n"),
    ],
)
def test_only_the_number_of_sheet_problems_is_logged(
    uploads, monkeypatch, tmp_path, capsys, problem_rows, logged
):
    # Run logs are public on GitHub, so names and sheet text stay out of them
    good = ["Alex", "x", "Mahuika", date(2026, 10, 19), date(2026, 10, 23)]
    bad = [
        ["Jamie", "x", "Mahuika", date(2026, 10, 19), date(2026, 10, 23)],
        ["Casey", "x", "Frontera", "early Nov", date(2026, 11, 13)],
    ]
    tabs = with_runs(good, *bad[:problem_rows])
    monkeypatch.setattr(
        hpc_gantt, "download_workbook", lambda sheet_id: make_xlsx(tabs)
    )
    assert update_chart("ID", NOW.date(), NOW, None, tmp_path / "c.png") == 0
    assert capsys.readouterr().err == logged
```

- [ ] **Step 2: Run it.** `TEST tests/test_cli.py -v`. Expected: the 1- and 2-problem cases FAIL, because the old `Sheet problem: …` lines are printed. The 0-problem case passes.
- [ ] **Step 3: Implement.** In `update_chart`, replace the loop that prints each problem with:

```python
if schedule.problems:
    count = len(schedule.problems)
    print(
        f"The sheet has {count} problem{'' if count == 1 else 's'}, listed at the bottom of the chart.",
        file=sys.stderr,
    )
```

- [ ] **Step 4: Run the tests.** `TEST`. Expected: all pass.
- [ ] **Step 5: Commit.** `git commit -am "fix: log only the number of sheet problems"`

---

### Task 10: Go live on GitHub Actions (with the user)

The user approved this on 2026-10-22:
- the public repo `ucgmsim/hpc_gantt_bot`;
- runs weekly, plus on demand;
- the sheet's link stays private.

Steps 5–7 publish and write to the team's Dropbox. They're done with that approval; anything beyond them needs a new go-ahead.

**Files:**
- Create `.github/workflows/update-chart.yml`.
- In `README.md`, replace "Deploy on mantle" and "Operating".
- Delete `deploy/`.

- [ ] **Step 1: Write the workflow.** `.github/workflows/update-chart.yml`:
  - **Triggers:** `schedule` with `cron: "17 17 * * 0"` (Monday 06:17 NZDT / 05:17 NZST), and `workflow_dispatch`.
  - **Permissions:** `permissions: {}` at the top level.
  - **Job `chart`:**
    - `environment: dropbox` and `contents: read`;
    - `actions/checkout` (SHA-pinned v7.0.1, `persist-credentials: false`);
    - `astral-sh/setup-uv` (SHA-pinned v10.3.1, `version: "0.11.28"`, `enable-cache: false`);
    - `apt-get install rclone`;
    - `uv run --script hpc_gantt.py`, with env:
      - `SHEET_ID` from its secret;
      - `RCLONE_CONFIG_DROPBOX_TYPE=dropbox`;
      - `RCLONE_CONFIG_DROPBOX_TOKEN` built as `{"refresh_token":"<secret>","expiry":"2000-01-01T00:00:00Z"}`.
  - **Job `keepalive`:** only on `schedule` events, with `actions: write`. It runs `gh api --method PUT repos/$GITHUB_REPOSITORY/actions/workflows/update-chart.yml/enable`.

  Lint it with `uvx --from actionlint-py actionlint`. Expected: no findings.
- [ ] **Step 2: README and clean-up.**
  - Rewrite the README's deployment and operating sections for GitHub Actions.
  - `git rm -r deploy`.
  - `TEST` passes.
  - Commit: "feat: run weekly on GitHub Actions instead of on mantle".
- [ ] **Step 3: Merge into main.** `git checkout main && git merge --ff-only feat/hpc-gantt`, then `TEST` on main.
- [ ] **Step 4: Remove the private details from all history.**
  - Back up first: `git bundle create <scratchpad>/before-scrub.bundle --all`.
  - Then run `git filter-repo --force` with:
    - `--replace-text`: the sheet ID becomes `<sheet ID>`, the team Google account's address goes, and the user's username becomes `<you>`;
    - `--replace-message`: the Claude-Session lines go;
    - `--invert-paths` on the two superseded 2026-10-19 Slack-bot docs.

    The last three are the user's choices of 2026-10-22.
  - Expected: none of them appears in any blob or commit message of `git rev-list --all`, the two docs are in no commit, and `TEST` passes.
- [ ] **Step 5: Publish.**
  - `gh repo create ucgmsim/hpc_gantt_bot --public`, add it as `origin`, then `git push -u origin main`.
  - Expected: the push starts one CI run, because `ci.yml` runs on pushes to `main`. It needs no secrets and should pass. The chart workflow doesn't start, because it has no push trigger.
- [ ] **Step 6: The environment and secrets.**
  - Create the `dropbox` environment with a deployment branch policy allowing only `main`.
  - Set `SHEET_ID` and `DROPBOX_REFRESH_TOKEN` by piping them into `gh secret set --env dropbox`, so they're never printed.
  - Set the repo's default workflow token to read-only *(final review 2)*.
  - Expected: `gh secret list --env dropbox` shows both names, and `gh api repos/ucgmsim/hpc_gantt_bot/environments/dropbox/deployment-branch-policies --jq '.branch_policies[].name'` lists only `main` *(final review 2)*.
- [ ] **Step 7: The first run.**
  - `gh workflow run update-chart.yml`, then `gh run watch`.
  - Expected:
    - the run succeeds;
    - its log ends with `Uploaded to dropbox:/QuakeCoRE/hpc_usage_gantt.png` and shows no sheet text and no secret values;
    - `rclone lsl` shows the file's new time;
    - the downloaded chart looks right;
    - reading the whole public log, including the step's env block, shows both secret values as `***` *(final review 2)*.
- [ ] **Step 8: The real share link.** This was Task 7 Step 5, and needs the user's go-ahead. Run `rclone link dropbox:/QuakeCoRE/hpc_usage_gantt.png` and give the link to the user for their Slack `/remind`.
- [ ] **Step 9: The first scheduled run.** After the next Monday morning, `gh run list --workflow update-chart.yml --event schedule` should show a success.

---

### Task 11: Adopt the team's shared CI (before Task 10 Step 4)

On 2026-10-22 the user decided to adopt `ucgmsim/meta-ci-action` v2 before the repo goes public. A trial on a scratch copy, with qcore's settings, found:
- pytest: 57 of 57 pass;
- deptry: clean;
- `ruff format`: would change 11 of 15 files;
- `ruff check`: 70 findings (58 missing argument type hints in tests, 7 import-order, 3 missing docstrings, 2 `datetime as D` aliases);
- ty: 8 errors;
- npdlint: 47 docstring findings.

**Files:**
- Create `pyproject.toml`, `uv.lock` and `.github/workflows/ci.yml`.
- Modify `hpc_gantt.py`, `tests/*.py`, `.github/workflows/update-chart.yml` and `README.md`.
- Delete `hpc_gantt.py.lock`.

- [ ] **Step 1: Reference renders.** Render three charts with the current code and its locked versions (`uv export --script hpc_gantt.py`):
  - the example chart;
  - an empty sheet;
  - a stress chart: a run past both edges, a finished run, a late right-aligned caption, `$` signs, macrons, and more than 8 problems.
- [ ] **Step 2: Make the repo a project.**
  - Write `pyproject.toml`:
    - the four dependencies;
    - a `dev` group with deptry, pytest, ruff and ty;
    - `[tool.uv] package = false`;
    - qcore's ruff, `numpydoc_validation` and `npdlint` settings.
  - Remove the script's PEP 723 header and shebang.
  - Run `uv lock` and delete `hpc_gantt.py.lock`. Compare the locked versions with the old lock.
  - The weekly workflow runs `uv run --locked --no-dev hpc_gantt.py`. Update the README's commands to match.
  - `TEST` becomes `uv run pytest -q`. Expected: 57 pass. Commit.
- [ ] **Step 3: Fix the findings.**
  - **ty:** narrow away None before building a `Run`, give `OVER_PLOT_TEXT` the type `dict[str, Any]`, and use matplotlib's string form for the bar's box style.
  - **ruff:** add the missing docstrings, type the test arguments, rename the `datetime as D` aliases, and run `ruff check --fix` for import order.
  - **npdlint:** add numpydoc Parameters and Returns sections.

  Expected: `ruff check`, `ty check` and `npdlint check` report nothing, and `TEST` passes. Commit.
- [ ] **Step 4: Run `ruff format`,** in a commit of its own. Expected: `ruff format --check` is clean, and `TEST` passes.
- [ ] **Step 5: Add `.github/workflows/ci.yml`.** It calls `ucgmsim/meta-ci-action/.github/workflows/ci.yml@v2` on pull requests and on pushes to `main`, with `python-version: "3.14"`. actionlint must be clean. Commit.
- [ ] **Step 6: Check everything locally, as the shared CI would.**
  - Run `uv sync --all-extras --dev`, then each of: `uv run --no-sync ruff check`, `ruff format --check`, `deptry .`, `pytest tests` and `ty check`, plus `uvx npdlint check`. Expected: all clean.
  - Re-render the reference charts. Expected: byte-identical to Step 1, in the same library versions.
- [ ] **Step 7: Merge into main** with `--ff-only`. Then Task 10 resumes at Step 4.
