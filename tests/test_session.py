"""The window's model: removing and restoring shapes, selecting, sizes, moving, and keeping manual changes when the
settings change."""
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from src.app.session import Session

SAMPLES = Path(__file__).parent / "samples"


@pytest.fixture(scope="module")
def barbarian():
    s = Session(Image.open(SAMPLES / "barbarian.png"), "x/barbarian.png")
    s.apply(s.analyse())
    return s


def fresh() -> Session:
    s = Session(Image.open(SAMPLES / "barbarian.png"), "x/barbarian.png")
    s.apply(s.analyse())
    return s


def test_summary_lists_groups(barbarian):
    assert barbarian.summary().startswith("6 frames of 48 x 84, 39 frames of 72 x 63, 35 frames of 80 x 84")
    assert barbarian.stem == "barbarian"


def test_frame_numbers_follow_reading_order(barbarian):
    nums = barbarian.frame_numbers()
    assert sorted(nums.values()) == list(range(1, 81))


def test_click_removes_and_restores_a_shape():
    s = fresh()
    shape = s.kept_in_order()[0]
    x, y = shape.box[0] + 2, shape.box[1] + 2
    assert s.shape_at(x, y) is shape
    s.toggle_shape(shape)
    assert shape.removed and sum(g.count for g in s.groups) == 79
    s.toggle_shape(shape)
    assert not shape.removed and sum(g.count for g in s.groups) == 80


def test_a_removed_shape_stays_removed_when_the_sheet_is_searched_again():
    s = fresh()
    box = s.kept_in_order()[3].box
    s.toggle_shape(s.shape_at(box[0] + 1, box[1] + 1))
    s.apply(s.analyse(replace(s.options, join_gap=4)), replace(s.options, join_gap=4))
    assert sum(g.count for g in s.groups) == 79


def test_a_restored_shape_stays_restored():
    s = fresh()
    gone = next(sh for sh in s.analysis.shapes if sh.removed)
    s.toggle_shape(gone)
    assert not gone.removed
    s.apply(s.analyse())
    assert not next(sh for sh in s.analysis.shapes if sh.box == gone.box).removed







def test_selection_is_dropped_when_a_shape_is_removed():
    s = fresh()
    shape = s.kept_in_order()[0]
    s.select([shape.box])
    s.toggle_shape(shape)
    assert not s.selected


def test_same_size_for_all_makes_one_group():
    s = fresh()
    o = replace(s.options, box_mode="same")
    s.options = o
    s.regroup()
    assert len(s.groups) == 1 and s.groups[0].count == 80


def test_shape_at_picks_the_smallest_shape():
    s = fresh()
    assert s.shape_at(-5, -5) is None


def test_group_selected_sprites_from_several_groups_into_one_box():
    s = fresh()
    order = s.kept_in_order()
    picked = order[:3] + order[10:12]                      # sprites from the 48 x 84 and 72 x 63 groups
    s.select([x.box for x in picked])
    w, h = max(x.width for x in picked), max(x.height for x in picked)
    assert s.selection_max_size() == (w, h)
    assert s.group_selected() == ""
    g = s.groups[s.group_of(picked[0])]
    assert (g.width, g.height) == (w, h) and all(x in g.shapes for x in picked)
    s.apply(s.analyse())                                   # the new group survives a new search
    g = s.groups[s.group_of(next(x for x in s.kept_in_order() if x.box == picked[0].box))]
    assert (g.width, g.height) == (w, h) and g.count >= 5


def test_group_selected_needs_a_selection():
    s = fresh()
    assert "Select some sprites" in s.group_selected()
