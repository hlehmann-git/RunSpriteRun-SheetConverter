"""The output preview and saving in the window (Qt offscreen)."""
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from src.app.main_window import MainWindow
from tests.test_window import _APP, centre, wait

SAMPLES = Path(__file__).parent / "samples"
RSR = Path("/home/claude/RunSpriteRun_experimental")


@pytest.fixture
def win(tmp_path):
    w = MainWindow()
    w.show()
    w.output.set_folder(tmp_path / "out")
    assert w.open_path(str(SAMPLES / "barbarian.png"))
    assert wait(_APP, lambda: w.session.analysis is not None and w.output.sheets)
    yield w
    w.close()
    w.deleteLater()
    _APP.processEvents()


def test_one_tab_per_size_group(win):
    names = [s.file_name for s in win.output.sheets]
    assert names == ["barbarian_RSR_48x84.png", "barbarian_RSR_72x63.png", "barbarian_RSR_80x84.png"]
    assert win.output.tabs.count() == 3
    assert win.output.save_button.text() == "Save Sheets (3 of 3)"
    assert not win.output.picture.pixmap().isNull()
    assert "barbarian_RSR_48x84.png  -  frame size 48 x 84" in win.output.info.text()
    assert win.output.tabs.tabText(0) == "48 x 84  -  6 frames"


def test_removing_a_sprite_updates_the_preview(win):
    first = win.session.kept_in_order()[0]
    QTest.mouseClick(win.view, Qt.LeftButton, Qt.NoModifier, centre(win, first))
    assert wait(_APP, lambda: win.output.sheets[0].count == 5)
    assert "5 frames" in win.output.tabs.tabText(0)


def test_untick_a_sheet_and_the_choice_survives_a_rebuild(win):
    win.output.tabs.setCurrentIndex(1)
    win.output.tick.setChecked(False)
    assert win.output.save_button.text() == "Save Sheets (2 of 3)"
    win.panel.centre.click()                                  # changes the sheets, not the number
    assert wait(_APP, lambda: win.output.sheets and not win.output.sheets[1].save)
    assert win.output.save_button.text() == "Save Sheets (2 of 3)"
    assert win.output.current_name() == "barbarian_RSR_72x63.png"


def test_there_is_no_target_system_and_colours_are_not_limited(win):
    assert not hasattr(win.output, "system_box")
    assert "colours used" in win.output.info.text() and "allows" not in win.output.info.text()


def test_save_writes_only_ticked_sheets(win, tmp_path):
    win.output.tabs.setCurrentIndex(0)
    win.output.tick.setChecked(False)
    win.save_now()
    saved = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert saved == ["barbarian_RSR_72x63.png", "barbarian_RSR_80x84.png"]
    assert "Saved 2 sheets" in win.output.saved.text()
    assert Image.open(tmp_path / "out" / saved[0]).size == win.output.sheets[1].image.size


def test_existing_file_asks_replace_or_cancel(win, tmp_path, monkeypatch):
    win.save_now()
    asked = []
    monkeypatch.setattr(win, "_ask_replace", lambda paths: asked.append(len(paths)) or False)
    path = tmp_path / "out" / "barbarian_RSR_48x84.png"
    path.write_bytes(b"old")
    win.save_now()
    assert asked == [3]
    assert path.read_bytes() == b"old"                       # Cancel wrote nothing
    assert win.output.saved.text() == "Nothing was saved."
    monkeypatch.setattr(win, "_ask_replace", lambda paths: True)
    win.save_now()
    assert Image.open(path).size == win.output.sheets[0].image.size


def test_saved_sheets_import_into_runspriterun(win, tmp_path):
    win.save_now()
    code = ("import sys\nfrom PIL import Image\n"
            "from src.core.sheet_import import find_grid, import_sheet\nfrom src.core.systems import get_system\n"
            "im = Image.open(sys.argv[1]); box = tuple(int(v) for v in sys.argv[2].split(','))\n"
            "g = find_grid(im, box); assert not g.error, g.error\n"
            "r = import_sheet(im, 't', g, (255, 0, 255), get_system('Amiga'))\n"
            "assert not r.rejected, r.rejected\nprint(len(r.frames))\n")
    if not RSR.exists():
        pytest.skip("RunSpriteRun folder not here")
    for s in win.output.sheets:
        r = subprocess.run([sys.executable, "-c", code, str(tmp_path / "out" / s.file_name),
                            ",".join(str(v) for v in s.box_colour)], cwd=RSR,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == str(s.count)


def test_ctrl_s_and_menu_follow_the_save_button(win):
    assert win.save_action.isEnabled()
    for i in range(win.output.tabs.count()):
        win.output.tabs.setCurrentIndex(i)
        win.output.tick.setChecked(False)
    assert not win.output.save_button.isEnabled()
    assert not win.save_action.isEnabled()


def test_a_folder_that_cannot_be_written_is_reported(win, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[2]))
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    win.output.set_folder(blocker / "inside")
    win.save_now()
    assert seen


def test_folder_box_is_one_line_with_the_middle_shortened(win):
    long = "C:\\Users\\someone\\Documents\\RunSpriteRun\\Converted\\a\\very\\long\\folder\\name\\indeed"
    win.output.set_folder(Path(long))
    win.output.resize(700, 300)
    label = win.output.folder_label
    label.setFixedWidth(200)
    _APP.processEvents()
    shown = label.displayed_text()
    assert "..." in shown or "\u2026" in shown
    assert shown.startswith("C") and shown.endswith("indeed")
    assert label.toolTip() == str(Path(long))
    assert not label.wordWrap()


def test_a_refused_size_names_the_frame_and_a_click_selects_it(tmp_path):
    img = Image.new("RGBA", (220, 90), (0, 0, 0, 0))
    for n in range(3):
        for y in range(10, 40):
            for x in range(10 + n * 50, 40 + n * 50):
                if abs(x - (25 + n * 50)) + abs(y - 25) <= 14:                 # a diamond, not a solid rectangle
                    img.putpixel((x, y), (200, 40 + n * 50, 40, 255))
    for x in range(10, 23):
        img.putpixel((x, 70), (255, 255, 255, 255))               # a 13 x 1 sliver
    path = tmp_path / "sliver.png"
    img.save(path)
    w = MainWindow()
    w.show()
    w.output.set_folder(tmp_path / "out")
    assert w.open_path(str(path))
    assert wait(_APP, lambda: w.session.analysis is not None and w.output.sheets)
    assert wait(_APP, lambda: "Frame" in w.output.messages.text() and "13 x 1" in w.output.messages.text())
    text = w.output.messages.text()
    assert "Sprite sizes must be 4 to 128 pixels." in text
    assert w.output.save_button.text() == "Save Sheets (1 of 1)"
    w.output._link("f:4")
    n = {box: num for box, num in w.session.frame_numbers().items()}
    assert [n[b] for b in w.session.selected] == [4]
    w.close()
    w.deleteLater()
    _APP.processEvents()
