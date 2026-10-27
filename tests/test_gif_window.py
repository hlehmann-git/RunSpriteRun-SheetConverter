"""The start screen, the launcher and the GIF window (Qt offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from src.app.gif_window import GifWindow
from src.app.launcher import Launcher
from src.app.main_window import MainWindow
from tests.test_gif import blob, make_gif
from tests.test_window import _APP, wait


@pytest.fixture
def gif_path(tmp_path):
    g = make_gif([blob(2, 2), blob(6, 5), blob(9, 3), blob(4, 8)], size=(30, 24))
    p = tmp_path / "walker.gif"
    g.save(p, save_all=True)
    # save_all on an opened GIF keeps its frames; rewrite from the in-memory frames to be sure
    frames = []
    g.seek(0)
    for i in range(g.n_frames):
        g.seek(i)
        frames.append(g.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=64))
    frames[0].save(p, "GIF", save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
    return str(p)


@pytest.fixture
def win(gif_path, tmp_path):
    w = GifWindow()
    w.show()
    w.output.set_folder(tmp_path / "out")
    assert w.open_path(gif_path)
    assert wait(_APP, lambda: w.output.sheets)
    yield w
    w.close()
    w.deleteLater()
    _APP.processEvents()


def thumb_point(win, index, x=1, y=1):
    r = win.strip.cell_rect(index)
    return QPoint(r.left() + 6 + x * win.strip.zoom + 1, r.top() + 6 + y * win.strip.zoom + 1)


def test_opening_shows_the_frames_and_one_sheet(win):
    assert "4 frames kept" in win.summary.text()
    assert "Box size:" in win.box_label.text()
    assert win.output.tabs.count() == 1
    assert win.output.sheets[0].count == 4
    assert win.output.sheets[0].file_name.startswith("walker_RSR_")
    assert "colours used" in win.output.info.text()
    assert not hasattr(win.output, "system_box")


def test_clicking_a_frame_drops_it_and_clicking_again_brings_it_back(win):
    QTest.mouseClick(win.strip, Qt.LeftButton, Qt.NoModifier, thumb_point(win, 1))
    assert "3 frames kept" in win.summary.text() and "1 dropped by you" in win.summary.text()
    assert wait(_APP, lambda: win.output.sheets[0].count == 3)
    QTest.mouseClick(win.strip, Qt.LeftButton, Qt.NoModifier, thumb_point(win, 1))
    assert "4 frames kept" in win.summary.text()


def test_trim_off_uses_the_whole_picture(win):
    win.trim.setChecked(False)
    assert "Box size: 30 x 24" in win.box_label.text()
    assert wait(_APP, lambda: win.output.sheets[0].width == 30)
    win.trim.setChecked(True)
    assert wait(_APP, lambda: win.output.sheets[0].width < 30)


def test_pick_the_background_colour_from_a_frame(win):
    win.bg_pick.click()
    assert win.strip.picking
    first = win.session.sheet.frames[0]
    ys, xs = (first.key == int(first.key[3, 3])).nonzero()                  # a pixel of the red blob
    QTest.mouseClick(win.strip, Qt.LeftButton, Qt.NoModifier, thumb_point(win, 0, int(xs[0]), int(ys[0])))
    assert not win.strip.picking and not win.bg_pick.isChecked()
    assert win.session.options.background is not None
    win.bg_auto.click()
    assert win.session.options.background is None


def test_save_writes_the_sheet_and_replace_is_asked(win, tmp_path, monkeypatch):
    win.save_now()
    files = list((tmp_path / "out").iterdir())
    assert len(files) == 1 and files[0].name.startswith("walker_RSR_")
    assert Image.open(files[0]).size == win.output.sheets[0].image.size
    asked = []
    monkeypatch.setattr(win, "_ask_replace", lambda paths: asked.append(len(paths)) or False)
    win.save_now()
    assert asked == [1] and win.output.saved.text() == "Nothing was saved."


def test_a_gif_larger_than_128_is_refused_and_nothing_can_be_saved(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[2]))
    big = Image.new("RGB", (130, 40), (20, 20, 20))
    for x in range(0, 130, 3):
        big.putpixel((x, x % 40), (200, 50, 50))                       # not an enlargement of anything smaller
    p = tmp_path / "big.gif"
    big.convert("P").save(p, "GIF")
    w = GifWindow()
    w.show()
    assert w.open_path(str(p))
    assert "Frames are 130 x 40. Sprite sizes must be 4 to 128 pixels." in w.error_label.text()
    assert seen and "cannot be converted" in seen[0] and "Frames are 130 x 40" in seen[0]      # a pop-up, not just a line
    assert not w.repeats.isEnabled()
    assert wait(_APP, lambda: "Frames are 130 x 40" in w.output.messages.text())
    assert not w.output.save_button.isEnabled() and not w.save_action.isEnabled()
    w.close()
    w.deleteLater()


def test_a_file_that_is_not_a_gif_is_refused(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[2]))
    p = tmp_path / "x.png"
    Image.new("RGB", (10, 10)).save(p)
    w = GifWindow()
    assert w.open_path(str(p)) is False
    assert seen and "could not be opened as a GIF" in seen[0]
    w.deleteLater()


def test_the_start_screen_offers_both_conversions_and_the_file_menu_returns_to_it(tmp_path):
    L = Launcher()
    L.show_start()
    assert L.start.gif_button.isVisible() and L.start.sheet_button.isVisible()
    L.start.gif_button.click()
    assert isinstance(L.current, GifWindow) and not L.start.isVisible()
    L.current.start_requested.emit()
    assert L.current is None and L.start.isVisible()
    L.start.sheet_button.click()
    assert isinstance(L.current, MainWindow)
    L.show_start()
    L.start.close()
    L.start.deleteLater()
    _APP.processEvents()


def test_an_enlarged_gif_opens_at_its_real_size_with_a_note(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[2]))
    frames = []
    for x in (4, 12, 20):
        im = Image.new("RGB", (64, 80), (90, 90, 90))
        im.putpixel((1, 1), (10, 200, 10))                              # odd single pixel: the true size is 64 x 80
        for i in range(7):
            for j in range(7):
                im.putpixel((x + i + 1, 31 + j), (200, 40, 40))
        frames.append(im.resize((256, 320), Image.NEAREST))
    p = tmp_path / "enlarged.gif"
    frames[0].save(p, "GIF", save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
    w = GifWindow()
    w.show()
    assert w.open_path(str(p))
    assert not seen and w.session.sheet.size == (64, 80) and len(w.session.sheet.frames) == 3
    assert "exact 4x enlargement" in w.error_label.text()
    assert wait(_APP, lambda: w.output.sheets and w.output.save_button.isEnabled())
    w.close()
    w.deleteLater()


def _enlarged_file(tmp_path, factor, size=(20, 16), name="blocky.gif"):
    from tests.test_gif import enlarged
    im = enlarged(factor, size=size)
    frames = []
    for i in range(im.n_frames):
        im.seek(i)
        frames.append(im.convert("RGB"))
    p = tmp_path / name
    frames[0].save(p, "GIF", save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
    return str(p)


def test_the_reduce_switch_and_pixel_size_rebuild_the_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    w = GifWindow()
    w.show()
    assert w.open_path(_enlarged_file(tmp_path, 3))                   # 60 x 48, an exact 3x of 20 x 16
    s = w.session
    assert w.reduce.isChecked() and w.reduce.isEnabled() and s.sheet.size == (20, 16)
    assert "3x enlargement" in w.scale_label.text()
    w.reduce.setChecked(False)                                        # keep it 1:1
    assert s.sheet.size == (60, 48) and "looks like a 3x enlargement" in w.error_label.text()
    w.reduce.setChecked(True)
    assert s.sheet.size == (20, 16)
    w.pixel_size.setCurrentIndex(w.pixel_size.findData(1))            # chosen by hand: 1x
    assert s.sheet.size == (60, 48) and not w.reduce.isEnabled()
    w.pixel_size.setCurrentIndex(0)                                   # back to Auto
    assert s.sheet.size == (20, 16) and w.reduce.isEnabled()
    assert wait(_APP, lambda: w.output.sheets and w.output.save_button.isEnabled())
    w.close()
    w.deleteLater()


def test_a_plain_gif_has_the_reduce_switch_greyed_out(win):
    assert not win.reduce.isEnabled() and win.pixel_size.isEnabled()
    assert "No enlargement found" in win.scale_label.text()
