import struct
import warnings
from datetime import date, datetime

from hpc_gantt import NZ, Run, Schedule, chart_subtitle, draw_chart, footer_lines, layout_chart

UPDATED = datetime(2026, 10, 20, 14, 0, tzinfo=NZ)
TUE = date(2026, 10, 20)


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_chart_subtitle():
    assert chart_subtitle(date(2026, 10, 5), date(2027, 1, 18), UPDATED) == (
        "Updated Tue 20 Oct 2026, 14:00 NZDT · showing 5 Oct 2026 – 17 Jan 2027")


def test_footer_lines():
    assert footer_lines([]) == []
    assert footer_lines(["a"]) == ["Problems in the sheet:", "a"]
    assert footer_lines([f"p{i}" for i in range(10)]) == ["Problems in the sheet:", *[f"p{i}" for i in range(8)], "…and 2 more"]


def test_draws_a_png(example_schedule, tmp_path):
    draw_chart(layout_chart(example_schedule, TUE), UPDATED, tmp_path / "chart.png")
    assert png_size(tmp_path / "chart.png")[0] == 1680


def test_height_grows_with_rows(example_schedule, tmp_path):
    many = [Run(i, "Alex", f"run {i}", "Mahuika", date(2026, 10, 20), date(2026, 10, 30)) for i in range(2, 32)]
    draw_chart(layout_chart(example_schedule, TUE), UPDATED, tmp_path / "few.png")
    draw_chart(layout_chart(Schedule(["Alex"], ["Mahuika"], many, []), TUE), UPDATED, tmp_path / "many.png")
    assert png_size(tmp_path / "many.png")[1] > png_size(tmp_path / "few.png")[1]


def test_empty_sheet_still_draws(tmp_path):
    draw_chart(layout_chart(Schedule([], [], [], []), TUE), UPDATED, tmp_path / "empty.png")
    assert png_size(tmp_path / "empty.png")[0] == 1680


def test_unicode_and_long_text_draw_without_warnings(tmp_path):
    s = Schedule(["Ōtautahi Ngā"], ["Mahuika"],
                 [Run(2, "Ōtautahi Ngā", "Kaikōura " * 30, "Mahuika", date(2026, 9, 1), date(2027, 3, 1))],
                 [f'Row {i} (?, ?): no person given' for i in range(12)])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        draw_chart(layout_chart(s, TUE), UPDATED, tmp_path / "text.png")


def test_dollar_signs_draw_literally(tmp_path):
    # "$...$" must not be read as maths: "$RUN_1_2" used to crash the hourly run with a mathtext ValueError
    s = Schedule(["Alex"], ["Cluster $A_1_2$"],
                 [Run(2, "Alex", "Rerun $RUN_1_2 and $RUN_1_3", "Cluster $A_1_2$", date(2026, 10, 20), date(2026, 10, 30))],
                 ['Row 9 (Alex, ?): start date "$X_1_2$" isn\'t a date'])
    draw_chart(layout_chart(s, TUE), UPDATED, tmp_path / "dollars.png")
    assert png_size(tmp_path / "dollars.png")[0] == 1680
