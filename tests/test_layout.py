from datetime import date

from hpc_gantt import Run, Schedule, caption, chart_window, layout_chart

TUE = date(2026, 10, 20)


def test_chart_window():
    assert chart_window(TUE) == (date(2026, 10, 5), date(2027, 1, 18))
    assert chart_window(date(2026, 10, 25)) == (date(2026, 10, 5), date(2027, 1, 18))


def test_lanes_follow_the_hpcs_tab(example_schedule):
    lanes = layout_chart(example_schedule, TUE).lanes
    assert [(l.hpc, l.top_row, l.rows, l.empty) for l in lanes] == [
        ("Mahuika", 0, 2, False), ("Frontera", 2, 1, False), ("Setonix", 3, 1, False), ("Test cluster", 4, 1, True)]


def test_bars(example_schedule):
    layout = layout_chart(example_schedule, TUE)
    assert layout.rows == 5 and layout.problems == example_schedule.problems
    assert [(b.row, b.start, b.end, b.cut_start, b.cut_end, b.finished, b.caption, b.label_x, b.label_align)
            for b in layout.bars] == [
        (0, date(2026, 10, 12), date(2026, 11, 2), False, False, False, "Alex · Hikurangi rupture scenarios", date(2026, 10, 12), "left"),
        (1, date(2026, 10, 26), date(2026, 11, 14), False, False, False, "Jordan · Alpine Fault ensemble, part 2", date(2026, 10, 26), "left"),
        (2, date(2026, 10, 19), date(2026, 10, 24), False, False, False, "Sam · Kaikōura validation runs", date(2026, 10, 19), "left"),
        (3, date(2026, 10, 28), date(2026, 11, 7), False, False, False, "Riley · Velocity model sensitivity tests", date(2026, 10, 28), "left"),
    ]


def test_finished_runs(example_schedule):
    bars = layout_chart(example_schedule, date(2026, 10, 26)).bars
    assert [(b.caption.split(" ·")[0], b.finished) for b in bars] == [
        ("Alex", False), ("Jordan", False), ("Sam", True), ("Riley", False)]


def test_run_longer_than_the_chart_is_cut_at_both_ends():
    s = Schedule(["Alex"], ["Mahuika"], [Run(2, "Alex", "Long campaign", "Mahuika", date(2026, 9, 1), date(2027, 3, 1))], [])
    (bar,) = layout_chart(s, TUE).bars
    assert (bar.start, bar.end, bar.cut_start, bar.cut_end, bar.label_x, bar.label_align) == (
        date(2026, 10, 5), date(2027, 1, 18), True, True, date(2026, 10, 5), "left")


def test_runs_outside_the_chart_leave_the_lane_empty():
    runs = [Run(2, "Alex", "", "Mahuika", date(2026, 9, 1), date(2026, 10, 4)),
            Run(3, "Alex", "", "Mahuika", date(2027, 1, 18), date(2027, 1, 20))]
    layout = layout_chart(Schedule(["Alex"], ["Mahuika"], runs, []), TUE)
    assert layout.bars == [] and layout.lanes[0].empty and layout.rows == 1


def test_late_starting_run_gets_a_right_aligned_caption():
    s = Schedule(["Alex"], ["Mahuika"], [Run(2, "Alex", "", "Mahuika", date(2026, 12, 20), date(2026, 12, 24))], [])
    (bar,) = layout_chart(s, TUE).bars
    assert (bar.label_x, bar.label_align) == (date(2026, 12, 25), "right")


def test_caption():
    assert caption("Alex", "Short") == "Alex · Short"
    assert caption("Alex", "") == "Alex"
    long = caption("Alex", "x" * 100)
    assert len(long) == 60 and long.endswith("…")


def test_no_hpcs_means_no_rows():
    assert layout_chart(Schedule([], [], [], []), TUE).rows == 0
