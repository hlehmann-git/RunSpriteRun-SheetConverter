"""v0.2.8: pieces of one sprite (such as sparkles) whose boxes overlap are merged; pieces can be merged into one
sprite box by hand, and split again; the program's own removals can be hidden. Only made-up pictures."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from src.app.session import Session
from src.core.detect import Options, analyse, boxes_overlap, merge_overlapping
from tests.helpers import blank

BG = (0, 0, 0)
STAR = (60, 90, 255)
WHITE = (240, 240, 255)


LIGHT = (150, 180, 255)
MID = (100, 130, 255)


def star(img, x, y, r=2):
    """A small sparkle shaded as real ones are: blue tips, two blues on the arms, a white centre."""
    for d in range(-r, r + 1):
        c = STAR if abs(d) == r else LIGHT if d > 0 else MID
        img.putpixel((x + d, y), c + (255,))
        img.putpixel((x, y + d), c + (255,))
    img.putpixel((x, y), WHITE + (255,))


def figure(img, x0, y0, w, h, seed=0):
    """A normal sprite: a block of mixed colours (not one plain colour, which would count as an empty cell)."""
    from tests.helpers import make_sprite, paste
    paste(img, make_sprite(np.random.default_rng(seed), w, h), x0, y0)


def sparkle_frame(img, x0, y0, seed):
    """One frame of a sparkle effect, about 25 x 32: stars that never touch, but whose boxes overlap, as on real
    sheets: two big stars meet corner to corner, and small stars sit inside a big star's box."""
    star(img, x0 + 6, y0 + 6, 6)                                       # box x0 .. x0+12
    star(img, x0 + 17, y0 + 17, 6)                                     # box x0+11 .. x0+23: corners overlap
    star(img, x0 + 11 + seed % 2, y0 + 22, 2)                          # inside the second star's box
    star(img, x0 + 3, y0 + 14, 1)                                      # inside nothing: joins through a chain
    star(img, x0 + 22, y0 + 25, 2)                                     # below; its box overlaps the second's


def effect_sheet():
    """Four sparkle frames in a row, 30 px apart, with a normal sprite beside them."""
    img = blank(170, 50, bg=BG)
    for n in range(4):
        sparkle_frame(img, 4 + n * 30, 6, n)
    figure(img, 142, 8, 20, 34)
    return img


# ---- the rule: overlapping boxes are one sprite --------------------------------------------------------------------
def test_pieces_with_overlapping_boxes_are_merged_again_and_again():
    from src.core.detect import Shape
    def sh(i, box):
        x0, y0, x1, y1 = box
        return Shape(i, box, "sprite", np.ones((y1 - y0 + 1, x1 - x0 + 1), bool), 1, 0)
    a, b, c, d = sh(1, (0, 0, 10, 10)), sh(2, (8, 8, 14, 14)), sh(3, (13, 0, 20, 4)), sh(4, (40, 0, 45, 5))
    out = merge_overlapping([a, b, c, d])                               # a+b overlap; then a+b overlaps c
    assert len(out) == 2
    merged = next(s for s in out if s.parts)
    assert merged.box == (0, 0, 20, 14) and len(merged.parts) == 3 and d in out
    assert not boxes_overlap(out[0].box, out[1].box)


def test_a_sparkle_effect_comes_out_as_whole_frames():
    a = analyse(effect_sheet(), Options())
    kept = sorted(a.kept(), key=lambda s: s.box[0])
    sparkles = [s for s in kept if s.box[0] < 140]
    assert len(sparkles) == 4                                           # one sprite per frame, no loose specks
    for n, s in enumerate(sparkles):
        assert s.box[0] == 4 + n * 30 and s.width >= 24 and s.height >= 27   # the whole frame, not one star
    for i, s in enumerate(sparkles):
        for o in kept[i + 1:]:
            assert not boxes_overlap(s.box, o.box)


def test_sprites_that_only_sit_close_are_not_merged():
    img = blank(80, 40, bg=BG)
    for n, x0 in enumerate((4, 24, 44)):                               # three sprites 4 px apart
        figure(img, x0, 5, 16, 25, n)
    a = analyse(img, Options())
    assert len(a.kept()) == 3 and not any(s.parts for s in a.kept())


# ---- by hand: Merge selected into one sprite, and Split -------------------------------------------------------------------
def pieces_sheet():
    """One effect frame made of three stars whose boxes do not overlap (the case the rule cannot see), and a normal
    sprite beside it."""
    img = blank(100, 40, bg=BG)
    for x, y in ((6, 6), (16, 18), (8, 30)):
        star(img, x, y)
    figure(img, 60, 6, 20, 28)
    return img


def open_session(img, opts=None):
    s = Session(img, "pieces.png", opts or Options())
    s.apply(s.analyse())
    return s


def test_merge_selected_pieces_into_one_sprite_box():
    s = open_session(pieces_sheet())
    stars = [x for x in s.analysis.kept() if x.box[0] < 40]
    assert len(stars) == 3
    s.select([x.box for x in stars])
    assert s.merge_selected() == ""
    kept = s.analysis.kept()
    merged = [x for x in kept if x.parts]
    assert len(kept) == 2 and len(merged) == 1
    assert merged[0].box == (4, 4, 18, 32) and merged[0].pixels == sum(p.pixels for p in stars)
    assert s.selected == {merged[0].box}
    home = next(g for g in s.groups if merged[0] in g.shapes)
    assert home.width >= 15 and home.height >= 29                       # its frame covers all three stars


def test_a_merge_is_kept_when_the_sheet_is_searched_again():
    s = open_session(pieces_sheet())
    s.select([x.box for x in s.analysis.kept() if x.box[0] < 40])
    s.merge_selected()
    s.apply(s.analyse(Options(join_gap=2)), Options(join_gap=2))      # a setting changed: searched again
    assert len(s.analysis.kept()) == 2 and sum(1 for x in s.analysis.kept() if x.parts) == 1


def test_split_brings_the_pieces_back_and_they_stay_split():
    s = open_session(pieces_sheet())
    s.select([x.box for x in s.analysis.kept() if x.box[0] < 40])
    s.merge_selected()
    assert s.can_split()
    s.split_selected()
    assert len(s.analysis.kept()) == 4 and len(s.selected) == 3 and not s.can_split()
    s.apply(s.analyse())
    assert len(s.analysis.kept()) == 4


def test_a_merge_the_program_made_can_be_split_too():
    s = open_session(effect_sheet())
    first = min((x for x in s.analysis.kept() if x.parts), key=lambda x: x.box[0])
    n = len(s.analysis.kept())
    s.select([first.box])
    s.split_selected()
    assert len(s.analysis.kept()) == n - 1 + len(first.parts)
    s.apply(s.analyse())                                                # not merged again on a re-search
    assert len(s.analysis.kept()) == n - 1 + len(first.parts)


def test_merging_needs_two_pieces():
    s = open_session(pieces_sheet())
    s.select([s.analysis.kept()[0].box])
    assert s.merge_selected() == "Select two or more pieces to merge."


# ---- the window --------------------------------------------------------------------------------------------------------
@pytest.fixture
def win(tmp_path):
    from src.app.main_window import MainWindow
    from tests.test_window import _APP, wait
    path = tmp_path / "pieces.png"
    pieces_sheet().save(path)
    w = MainWindow()
    w.show()
    w.open_path(str(path))
    assert wait(_APP, lambda: w.session and w.session.analysis is not None)
    yield w
    w.close()
    w.deleteLater()
    _APP.processEvents()


def test_the_merge_and_split_buttons(win):
    s = win.session
    assert not win.panel.merge_btn.isEnabled() and not win.panel.split_btn.isEnabled()
    win._rect_selected(0, 0, 40, 39, False)                            # drag a rectangle round the three stars
    assert len(s.selected) == 3 and win.panel.merge_btn.isEnabled()
    win.panel.merge_btn.click()
    assert len(s.analysis.kept()) == 2 and win.panel.split_btn.isEnabled() and not win.panel.merge_btn.isEnabled()
    win.panel.split_btn.click()
    assert len(s.analysis.kept()) == 4


def test_the_programs_removals_are_hidden_until_switched_on(tmp_path):
    from src.app.main_window import MainWindow
    from tests.test_window import _APP, wait
    img = pieces_sheet()
    for y in range(36, 39):                                            # a long thin line: removed as a "picture"
        for x in range(0, 100):
            img.putpixel((x, y), (90, 90, 90, 255))
    big = Image.new("RGBA", (300, 60), BG + (255,))
    big.paste(img, (0, 0))
    for x in range(0, 300):
        big.putpixel((x, 50), (90, 90, 90, 255))
    path = tmp_path / "lined.png"
    big.save(path)
    w = MainWindow()
    w.show()
    w.open_path(str(path))
    assert wait(_APP, lambda: w.session and w.session.analysis is not None)
    s = w.session
    line = next(x for x in s.analysis.shapes if x.removed and x.width > 128)
    assert not w.show_removed.isChecked() and not w.view.show_removed
    assert s.shape_at(150, 50, include_removed=False) is None          # hidden: a click there does nothing
    w._shape_clicked(150, 50, False)
    assert line.removed
    w.show_removed.setChecked(True)
    assert w.view.show_removed
    w._shape_clicked(150, 50, False)                                   # shown: a click brings it back
    assert not line.removed
    w.close()
    w.deleteLater()


def test_a_shape_you_remove_is_painted_out_and_ctrl_z_brings_it_back(win):
    s = win.session
    sprite = next(x for x in s.analysis.kept() if x.box[0] >= 60)
    cx, cy = (sprite.box[0] + sprite.box[2]) // 2, (sprite.box[1] + sprite.box[3]) // 2
    win._shape_clicked(cx, cy, False)
    assert sprite.removed and s.shape_at(cx, cy, include_removed=False) is None
    pic = win.view._picture()
    assert pic.pixelColor(cx, cy).getRgb()[:3] == BG                   # gone from the picture
    win.undo_click()
    assert not sprite.removed
    assert win.view._picture().pixelColor(cx, cy).getRgb()[:3] != BG    # back again
    win._shape_clicked(cx, cy, False)
    win.show_removed.setChecked(True)
    assert win.view._picture().pixelColor(cx, cy).getRgb()[:3] != BG    # shown again (with its cross)


def test_the_programs_removals_are_painted_out_too(tmp_path):
    from src.app.main_window import MainWindow
    from tests.test_window import _APP, wait
    img = pieces_sheet()
    big = Image.new("RGBA", (240, 70), BG + (255,))
    big.paste(img, (0, 0))
    for x in range(0, 240):                                             # a long line: removed as a "picture"
        big.putpixel((x, 60), (90, 90, 90, 255))
    path = tmp_path / "words.png"
    big.save(path)
    w = MainWindow()
    w.show()
    w.open_path(str(path))
    assert wait(_APP, lambda: w.session and w.session.analysis is not None)
    text = [x for x in w.session.analysis.shapes if x.removed and x.kind == "sprite"]
    assert text
    pic = w.view._picture()
    for x in text:
        ys, xs = x.mask.nonzero()
        assert pic.pixelColor(x.box[0] + int(xs[0]), x.box[1] + int(ys[0])).getRgb()[:3] == BG
    w.close()
    w.deleteLater()
