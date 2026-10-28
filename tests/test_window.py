"""The converter window, run without showing a screen (Qt offscreen)."""
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.app.main_window import MainWindow

SAMPLES = Path(__file__).parent / "samples"


_APP = QApplication.instance() or QApplication([])      # lives until Python exits, after every window is gone


@pytest.fixture(scope="module")
def app():
    return _APP


def wait(app, cond, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def win(app):
    w = MainWindow()
    w.show()
    assert w.open_path(str(SAMPLES / "barbarian.png"))
    assert wait(app, lambda: w.session.analysis is not None)
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def drag(view, a, b):
    """A left-button drag from a to b (QTest.mouseMove does not hold the button down)."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    def ev(kind, p, button, buttons):
        return QMouseEvent(kind, QPointF(p), QPointF(view.mapToGlobal(p)), button, buttons, Qt.NoModifier)
    QApplication.sendEvent(view, ev(QEvent.MouseButtonPress, a, Qt.LeftButton, Qt.LeftButton))
    QApplication.sendEvent(view, ev(QEvent.MouseMove, b, Qt.NoButton, Qt.LeftButton))
    QApplication.sendEvent(view, ev(QEvent.MouseButtonRelease, b, Qt.LeftButton, Qt.NoButton))


def centre(win, shape):
    z = win.view.zoom
    return QPoint((shape.box[0] + shape.box[2]) // 2 * z + 1, (shape.box[1] + shape.box[3]) // 2 * z + 1)


def test_opening_shows_the_groups(win):
    assert win.summary.text().startswith("6 frames of 48 x 84, 39 frames of 72 x 63")
    assert "barbarian.png" in win.title_label.text()
    assert win.panel.cell_text.text() == "#FF00FF"


def test_click_removes_a_shape_and_the_summary_follows(win):
    first = win.session.kept_in_order()[0]
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.NoModifier, centre(win, first))
    assert first.removed
    assert "5 frames of 48 x 84" in win.summary.text()
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.NoModifier, centre(win, first))
    assert first.removed                                    # painted out: a second click does nothing
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)       # Ctrl+Z brings it back
    assert not first.removed and "6 frames of 48 x 84" in win.summary.text()
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.NoModifier, centre(win, first))
    win.show_removed.setChecked(True)                       # shown again with its cross: a click restores it
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.NoModifier, centre(win, first))
    assert not first.removed


def test_ctrl_click_selects_and_enables_the_group_button(win):
    a, b = win.session.kept_in_order()[:2]
    assert not win.panel.group_btn.isEnabled()
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.ControlModifier, centre(win, a))
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.ControlModifier, centre(win, b))
    assert len(win.session.selected) == 2
    assert win.panel.group_btn.isEnabled()
    assert win.panel.selected_head.text() == "Selected sprites: 2"


def test_drag_a_rectangle_selects_the_sprites_inside(win):
    shapes = win.session.kept_in_order()[:6]                  # the first row of six
    z = win.view.zoom
    x1 = max(s.box[2] for s in shapes) * z + 2
    y1 = max(s.box[3] for s in shapes) * z + 2
    drag(win.view, QPoint(0, 0), QPoint(x1, y1))
    assert len(win.session.selected) == 6




def test_same_size_for_all_changes_at_once_without_a_new_search(win):
    win.panel.same.setChecked(True)
    assert "80 frames of 80 x 84" in win.summary.text()
    win.panel.estimate.setChecked(True)
    assert "39 frames of 72 x 63" in win.summary.text()


def test_changing_join_gap_searches_again(app, win):
    before = win._serial
    win.panel.join_gap.setValue(0)
    assert win._serial >= before
    assert wait(app, lambda: win.session.options.join_gap == 0 and win.summary.text() != "Working...")
    assert "frames" in win.summary.text()


def test_pick_the_background_colour(app, win):
    win.panel.bg_pick.click()
    assert win.view.picking
    pink_x, pink_y = win.session.kept_in_order()[0].box[:2]
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.NoModifier, QPoint(pink_x * win.view.zoom + 1, pink_y * win.view.zoom + 1))
    assert not win.view.picking
    assert wait(app, lambda: win.session.options.background is not None and win.summary.text() != "Working...")
    win.panel.bg_auto.click()
    assert wait(app, lambda: win.session.options.background is None and win.summary.text() != "Working...")


def test_zoom_buttons(win):
    z = win.view.zoom
    win.zoom_in.click()
    assert win.view.zoom == min(8, z + 1)
    for _ in range(10):
        win.zoom_out.click()
    assert win.view.zoom == 1


def test_a_bad_file_is_refused_kindly(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[2]))
    w = MainWindow()
    bad = tmp_path / "x.png"
    bad.write_bytes(b"not a picture")
    assert w.open_path(str(bad)) is False
    w.close()
    w.deleteLater()
    assert seen and "could not be opened" in seen[0]


def test_group_button_puts_selected_sprites_in_one_box(win):
    a, b = win.session.kept_in_order()[0], win.session.kept_in_order()[20]
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.ControlModifier, centre(win, a))
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.ControlModifier, centre(win, b))
    assert win.panel.group_btn.isEnabled()
    assert "Group the 2 selected sprites into the same sized box (" in win.panel.group_label.text()
    win.panel.group_btn.click()
    g = win.session.groups[win.session.group_of(a)]
    assert g is win.session.groups[win.session.group_of(b)] and g.count >= 2
    assert (g.width, g.height) == (max(a.width, b.width), max(a.height, b.height))
    assert f"{g.count} frames of {g.width} x {g.height}" in win.summary.text()


def _select_two(win):
    a, b = win.session.kept_in_order()[0], win.session.kept_in_order()[20]
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.ControlModifier, centre(win, a))
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.ControlModifier, centre(win, b))
    assert len(win.session.selected) == 2


def test_escape_clears_the_selection_without_asking(win):
    _select_two(win)
    QTest.keyClick(win, Qt.Key_Escape)
    assert not win.session.selected
    assert win.panel.selected_head.text() == "Selected sprites: none"
    assert not win.panel.group_btn.isEnabled()


def test_escape_also_stops_picking_a_colour(win):
    win.panel.bg_pick.click()
    assert win.view.picking
    QTest.keyClick(win, Qt.Key_Escape)
    assert not win.view.picking and not win.panel.bg_pick.isChecked()


def test_clicking_empty_space_clears_the_selection(win):
    _select_two(win)
    QTest.mouseClick(win.output.info, Qt.LeftButton, Qt.NoModifier, QPoint(2, 2))      # a label in the output panel
    assert not win.session.selected


def test_clicking_empty_space_in_the_source_picture_clears_it(win):
    _select_two(win)
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.NoModifier, QPoint(win.view.width() - 2, win.view.height() - 2))
    assert not win.session.selected


def test_ctrl_click_on_empty_space_keeps_the_selection(win):
    _select_two(win)
    QTest.mouseClick(win.output.info, Qt.LeftButton, Qt.ControlModifier, QPoint(2, 2))
    assert len(win.session.selected) == 2


def test_clicking_a_control_keeps_the_selection(win):
    _select_two(win)
    QTest.mouseClick(win.panel.centre, Qt.LeftButton)
    QTest.mouseClick(win.panel.remove_text, Qt.LeftButton, Qt.NoModifier, QPoint(3, 3))
    QTest.mouseClick(win.zoom_in, Qt.LeftButton)
    assert len(win.session.selected) == 2


def test_clicking_a_removed_shape_restores_it_and_keeps_the_selection(win):
    _select_two(win)
    third = win.session.kept_in_order()[5]
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.NoModifier, centre(win, third))      # removes it (a click on a sprite)
    assert third.removed
    assert len(win.session.selected) == 2
    win.show_removed.setChecked(True)
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.NoModifier, centre(win, third))
    assert not third.removed and len(win.session.selected) == 2
