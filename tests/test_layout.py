import numpy as np

from src.core import layout
from src.core.detect import Options, analyse
from tests.helpers import blank, make_sprite, paste


def sheet_with(rows):
    """rows: list of lists of (w, h); returns (sheet, expected boxes in reading order)."""
    rng = np.random.default_rng(1)
    total_w = max(sum(w + 10 for w, _ in r) for r in rows) + 20
    sheet = blank(total_w, sum(max(h for _, h in r) + 12 for r in rows) + 20)
    boxes, y = [], 10
    for r in rows:
        x, bottom = 10, y + max(h for _, h in r)
        for w, h in r:
            paste(sheet, make_sprite(rng, w, h), x, bottom - h)           # feet on a common line
            boxes.append((x, bottom - h, x + w - 1, bottom - 1))
            x += w + 10
        y = bottom + 12
    return sheet, boxes


def test_frames_are_numbered_left_to_right_then_top_to_bottom():
    sheet, boxes = sheet_with([[(20, 30), (24, 26), (18, 34)], [(22, 28), (30, 20)]])
    a = analyse(sheet)
    layout.assign_rows(a.kept())
    order = layout.reading_order(a.kept())
    assert [s.box for s in order] == boxes
    assert [s.row for s in order] == [0, 0, 0, 1, 1]


def test_estimate_makes_one_group_per_row_and_the_widest_and_tallest_sets_the_box():
    sheet, _ = sheet_with([[(20, 30), (24, 26), (18, 34)], [(60, 50), (64, 44)]])
    o = Options(size_tolerance=0)
    groups = layout.make_groups(analyse(sheet, o), o)
    assert [(g.width, g.height, g.count) for g in groups] == [(24, 34, 3), (64, 50, 2)]


def test_size_tolerance_merges_nearly_equal_sizes_into_the_larger():
    sheet, _ = sheet_with([[(20, 30)], [(26, 33)], [(70, 60)]])
    o = Options(size_tolerance=8)
    groups = layout.make_groups(analyse(sheet, o), o)
    assert [(g.width, g.height, g.count) for g in groups] == [(26, 33, 2), (70, 60, 1)]
    o0 = Options(size_tolerance=5)
    groups = layout.make_groups(analyse(sheet, o0), o0)
    assert len(groups) == 3                                                  # 6 px apart: not merged at 5


def test_same_size_for_all_makes_one_group():
    sheet, _ = sheet_with([[(20, 30), (24, 26)], [(60, 50)]])
    o = Options(box_mode="same")
    groups = layout.make_groups(analyse(sheet, o), o)
    assert [(g.width, g.height, g.count) for g in groups] == [(60, 50, 3)]


def test_a_group_that_is_too_big_has_a_message():
    rng = np.random.default_rng(2)
    sheet = blank(400, 100)
    paste(sheet, make_sprite(rng, 120, 40), 10, 10)
    a = analyse(sheet, Options(max_shape=300))
    o = Options(max_shape=300)
    g = layout.make_groups(a, o)[0]
    assert g.problem == ""                                                   # 120 is allowed
    layout.constrain(g)
    assert (g.width, g.height, g.problem) == (120, 40, "")
    g.width = 130                                                            # a box wider than 128 cannot be made
    g.problem = layout._fits(g.width, g.height)
    assert "4 to 128" in g.problem
    layout.constrain(g)
    assert (g.width, g.height, g.problem) == (120, 40, "")


def test_more_than_120_frames_split_into_sheets():
    g = layout.SizeGroup(10, 10, list(range(250)))
    parts = layout.sheet_parts(g)
    assert [len(p) for p in parts] == [120, 120, 10]
