from datetime import date

from helpers import TUE

from hpc_gantt import Bar, Lane, Run, Schedule, caption, chart_window, layout_chart


def test_chart_window():
    assert chart_window(TUE) == (date(2026, 10, 5), date(2027, 1, 18))
    assert chart_window(date(2026, 10, 25)) == (date(2026, 10, 5), date(2027, 1, 18))


def test_lanes_follow_the_hpcs_tab(example_schedule: Schedule):
    assert layout_chart(example_schedule, TUE).lanes == [
        Lane("Mahuika", 0, 2, False), Lane("Frontera", 2, 1, False), Lane("Setonix", 3, 1, False), Lane("Test cluster", 4, 1, True)]


def test_bars(example_schedule: Schedule):
    layout = layout_chart(example_schedule, TUE)
    assert layout.rows == 5 and layout.problems == example_schedule.problems
    assert layout.bars == [
        Bar(0, date(2026, 10, 12), date(2026, 11, 2), False, "Alex · Hikurangi rupture scenarios", date(2026, 10, 12), "left"),
        Bar(1, date(2026, 10, 26), date(2026, 11, 14), False, "Jordan · Alpine Fault ensemble, part 2", date(2026, 10, 26), "left"),
        Bar(2, date(2026, 10, 19), date(2026, 10, 24), False, "Sam · Kaikōura validation runs", date(2026, 10, 19), "left"),
        Bar(3, date(2026, 10, 28), date(2026, 11, 7), False, "Riley · Velocity model sensitivity tests", date(2026, 10, 28), "left"),
    ]


def test_finished_runs(example_schedule: Schedule):
    bars = layout_chart(example_schedule, date(2026, 10, 26)).bars
    assert [(b.caption.split(" ·")[0], b.finished) for b in bars] == [
        ("Alex", False), ("Jordan", False), ("Sam", True), ("Riley", False)]


def test_run_longer_than_the_chart_keeps_its_caption_inside():
    s = Schedule(["Mahuika"], [Run(2, "Alex", "Long campaign", "Mahuika", date(2026, 9, 1), date(2027, 3, 1))], [])
    (bar,) = layout_chart(s, TUE).bars
    # the bar spans the whole run (the plot clips it square at both edges); the caption starts at the chart's first day
    assert (bar.start, bar.end, bar.label_x, bar.label_align) == (date(2026, 9, 1), date(2027, 3, 2), date(2026, 10, 5), "left")


def test_runs_outside_the_chart_leave_the_lane_empty():
    runs = [Run(2, "Alex", "", "Mahuika", date(2026, 9, 1), date(2026, 10, 4)),
            Run(3, "Alex", "", "Mahuika", date(2027, 1, 18), date(2027, 1, 20))]
    layout = layout_chart(Schedule(["Mahuika"], runs, []), TUE)
    assert layout.bars == [] and layout.lanes[0].empty and layout.rows == 1


def test_late_starting_run_gets_a_right_aligned_caption():
    s = Schedule(["Mahuika"], [Run(2, "Alex", "", "Mahuika", date(2026, 12, 20), date(2026, 12, 24))], [])
    (bar,) = layout_chart(s, TUE).bars
    assert (bar.label_x, bar.label_align) == (date(2026, 12, 25), "right")


def test_caption():
    assert caption("Alex", "Short") == "Alex · Short"
    assert caption("Alex", "") == "Alex"
    long = caption("Alex", "x" * 100)
    assert len(long) == 60 and long.endswith("…")


def test_no_hpcs_means_no_rows():
    assert layout_chart(Schedule([], [], []), TUE).rows == 0
