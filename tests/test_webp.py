"""WebP files (still and animated, lossy and lossless) and colour clean-up. Only made-up pictures are used."""
import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from src.core import colours, gif
from src.app.session import Session

PALETTE = [(30, 60, 30), (200, 40, 40), (40, 40, 200), (240, 220, 120), (90, 50, 20), (250, 250, 250)]
DETAIL = (255, 0, 255)          # one real one-pixel detail


def art(seed=1, scale=2, detail=True) -> Image.Image:
    """Pixel art in six colours (plus one tiny detail), drawn at `scale`."""
    rng = np.random.default_rng(seed)
    a = np.zeros((48, 64, 3), np.uint8)
    a[:] = PALETTE[0]
    for _ in range(30):
        x, y = rng.integers(0, 56), rng.integers(0, 40)
        a[y:y + rng.integers(2, 8), x:x + rng.integers(2, 8)] = PALETTE[rng.integers(1, 6)]
    if detail:
        a[5, 5] = DETAIL
    im = Image.fromarray(a)
    return im.resize((64 * scale, 48 * scale), Image.NEAREST).convert("RGBA")


def webp_bytes(frames, **kw) -> bytes:
    b = io.BytesIO()
    frames[0].save(b, "WEBP", save_all=len(frames) > 1, append_images=frames[1:], **kw)
    return b.getvalue()


def rgba(data: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGBA")).copy()


def colour_set(f: np.ndarray) -> set:
    s = f[..., 3] >= 128
    a = f[..., :3].astype(np.int64)
    return set(((a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2])[s].tolist())


# ---- telling lossy from lossless ------------------------------------------------------------------------------------
def test_webp_kind_tells_lossy_from_lossless():
    im = art()
    assert colours.webp_kind(webp_bytes([im], quality=80)) == "lossy"
    assert colours.webp_kind(webp_bytes([im], lossless=True)) == "lossless"
    assert colours.webp_kind(webp_bytes([im, art(2)], quality=80)) == "lossy"           # animated
    assert colours.webp_kind(webp_bytes([im, art(2)], lossless=True)) == "lossless"
    png = io.BytesIO()
    im.save(png, "PNG")
    assert colours.webp_kind(png.getvalue()) == ""
    assert colours.webp_kind(b"RIFF") == ""


def test_webp_kind_reads_a_file(tmp_path):
    p = tmp_path / "a.webp"
    p.write_bytes(webp_bytes([art()], quality=70))
    assert colours.webp_kind(p) == "lossy"
    assert colours.webp_kind(tmp_path / "missing.webp") == ""


# ---- clean-up ---------------------------------------------------------------------------------------------------------
def test_a_lossless_webp_keeps_every_colour_exactly():
    im = art()
    f = rgba(webp_bytes([im], lossless=True))
    assert np.array_equal(f, np.asarray(im))


@pytest.mark.parametrize("quality", [95, 80, 60])
def test_clean_up_brings_a_lossy_webp_back_near_its_palette(quality):
    f = rgba(webp_bytes([art()], quality=quality))
    before = colours.colour_count([f])
    res = colours.clean_up([f], "Medium")
    assert before > 100 and res.before == before
    assert res.after <= len(PALETTE) + 1 + 4                 # the real palette is 7 colours
    assert colours.colour_count(res.frames) == res.after


def test_clean_up_only_uses_colours_already_in_the_picture():
    f = rgba(webp_bytes([art()], quality=70))
    res = colours.clean_up([f], "High")
    assert colour_set(res.frames[0]) <= colour_set(f)


def test_a_small_real_detail_survives():
    f = rgba(webp_bytes([art()], quality=90))
    out = colours.clean_up([f], "Medium").frames[0]
    spot = out[10:12, 10:12, :3].reshape(-1, 3)              # the 2 x 2 detail at (5, 5), drawn at 2x
    assert (spot[:, 0] > 150).all() and (spot[:, 2] > 150).all() and (spot[:, 1] < 100).all()
    assert len({tuple(p) for p in spot.tolist()}) == 1       # one colour, not smudged


def test_stronger_settings_merge_more():
    f = rgba(webp_bytes([art(3)], quality=70))
    low, medium, high = (colours.clean_up([f], s).after for s in ("Low", "Medium", "High"))
    assert high <= low and high <= medium + 1


def test_transparency_is_kept_and_edges_made_solid():
    im = art()
    a = np.asarray(im).copy()
    a[:20, :30, 3] = 0                                       # a transparent corner
    a[30, 40, 3] = 200                                       # one partly see-through pixel
    f = rgba(webp_bytes([Image.fromarray(a, "RGBA")], quality=80))
    out = colours.clean_up([f], "Medium").frames[0]
    assert (out[:20, :30, 3] == 0).all()
    assert set(np.unique(out[..., 3]).tolist()) <= {0, 255}


def test_all_frames_of_an_animation_share_one_palette():
    frames = [rgba(webp_bytes([art(s)], quality=75)) for s in (1, 2)]
    res = colours.clean_up(frames, "Medium")
    assert colour_set(res.frames[0]) | colour_set(res.frames[1]) == set().union(*map(colour_set, res.frames))
    assert colours.colour_count(res.frames) == res.after


def test_a_big_lossy_sheet_is_cleaned_quickly():
    import time
    big = Image.new("RGBA", (1024, 768))
    for i, (x, y) in enumerate((x, y) for x in range(0, 1024, 128) for y in range(0, 768, 96)):
        big.paste(art(i % 7), (x, y))
    f = rgba(webp_bytes([big], quality=75))
    t = time.time()
    res = colours.clean_up([f], "Medium")
    assert time.time() - t < 20 and res.after < 40


def test_the_note_says_what_happened():
    assert "cleaned up to 9 (Medium)" in colours.clean_note(True, 300, 9, "Medium")
    assert "Tick Clean up colours" in colours.clean_note(True, 300, None, None)
    assert "Tick Reduce colours" in colours.clean_note(False, 12, None, None)
    assert "reduced to 5 (Low)" in colours.clean_note(False, 12, 5, "Low")


# ---- the sprite sheet session -----------------------------------------------------------------------------------------
def test_a_lossy_webp_sheet_is_cleaned_up_by_default(tmp_path):
    p = tmp_path / "sheet.webp"
    p.write_bytes(webp_bytes([art()], quality=75))
    s = Session(Image.open(p), p)
    assert s.lossy and s.cleanup == "Medium" and s.colours_after < 15 < s.colours_before
    s.set_cleanup(None)
    assert s.image is s.original and s.colours_after == s.colours_before
    assert "Tick Clean up colours" in s.colours_text()


def test_a_lossless_webp_sheet_is_not_touched(tmp_path):
    p = tmp_path / "sheet.webp"
    p.write_bytes(webp_bytes([art()], lossless=True))
    s = Session(Image.open(p), p)
    assert not s.lossy and s.cleanup is None and s.colours_before == 7
    assert np.array_equal(np.asarray(s.image), np.asarray(art()))
    assert "Tick Reduce colours" in s.colours_text()


def test_an_exact_colour_sheet_can_still_be_reduced_by_choice(tmp_path):
    p = tmp_path / "sheet.png"
    art().save(p)
    s = Session(Image.open(p), p)
    assert not s.lossy and s.cleanup is None and s.colours_before == 7      # off by default: nothing is smudged
    s.set_cleanup("Low")
    assert s.cleanup == "Low" and s.colours_after <= s.colours_before
    assert "reduced to" in s.colours_text()


# ---- animated WebP ----------------------------------------------------------------------------------------------------
def test_an_animated_webp_is_read_frame_by_frame():
    data = webp_bytes([art(1), art(2), art(3)], lossless=True, duration=80)
    s = gif.read_gif(Image.open(io.BytesIO(data)))
    assert not s.error and len(s.frames) == 3
    assert s.size == (64, 48) and s.factor == 2                    # the test art is drawn at 2x, and is found to be
    assert not s.lossy and s.cleanup is None


def test_a_lossy_enlarged_webp_is_cleaned_then_reduced_to_its_real_size():
    frames = [art(seed, scale=3) for seed in (1, 2, 3)]            # 192 x 144: a 3x enlargement of 64 x 48
    data = webp_bytes(frames, quality=85, duration=80)
    s = gif.read_gif(Image.open(io.BytesIO(data)), lossy=True)
    assert s.cleanup == "Medium" and s.colours_after < 20 < s.colours_before
    assert s.factor == 3 and s.size == (64, 48) and not s.error
    gif.set_cleanup(s, None)                                       # without clean-up the smudge hides the enlargement
    assert s.colours_after == s.colours_before


# ---- windows and launching --------------------------------------------------------------------------------------------
def test_the_sheet_window_shows_the_clean_up_switch(tmp_path, monkeypatch):
    from src.app.main_window import MainWindow
    from tests.test_window import _APP, wait
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    p = tmp_path / "sheet.webp"
    p.write_bytes(webp_bytes([art()], quality=75))
    w = MainWindow()
    w.show()
    assert w.open_path(str(p))
    c = w.panel.cleanup
    assert c.switch.isEnabled() and c.switch.isChecked() and "cleaned up to" in c.note.text()
    assert wait(_APP, lambda: w.session.analysis is not None)
    c.switch.setChecked(False)
    assert w.session.cleanup is None and "Tick Clean up colours" in c.note.text()
    c.switch.setChecked(True)
    c.strength.setCurrentIndex(c.strength.findData("High"))
    assert w.session.cleanup == "High"
    assert wait(_APP, lambda: w.session.analysis is not None and w.output.sheets)
    w.close()
    w.deleteLater()


def test_the_animation_window_opens_an_animated_webp(tmp_path, monkeypatch):
    from src.app.gif_window import GifWindow
    from tests.test_window import _APP, wait
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    p = tmp_path / "walk.webp"
    p.write_bytes(webp_bytes([art(s, scale=3) for s in (1, 2, 3)], quality=85, duration=80))
    w = GifWindow()
    w.show()
    assert w.open_path(str(p))
    assert w.cleanup.switch.isChecked() and w.session.sheet.factor == 3 and w.reduce.isChecked()
    w.cleanup.switch.setChecked(False)
    assert w.session.sheet.cleanup is None
    w.cleanup.switch.setChecked(True)
    assert wait(_APP, lambda: w.output.sheets and w.output.save_button.isEnabled())
    w.close()
    w.deleteLater()


def test_a_plain_png_is_offered_reduce_colours_unticked(tmp_path):
    from src.app.main_window import MainWindow
    p = tmp_path / "sheet.png"
    art().save(p)
    w = MainWindow()
    w.show()
    assert w.open_path(str(p))
    assert w.panel.cleanup.switch.isEnabled() and not w.panel.cleanup.switch.isChecked()
    assert w.panel.cleanup.switch.text() == "Reduce colours"
    w.close()
    w.deleteLater()


def test_an_animated_webp_opens_in_the_animation_window(tmp_path):
    import main
    still, anim = tmp_path / "still.webp", tmp_path / "anim.webp"
    still.write_bytes(webp_bytes([art()], lossless=True))
    anim.write_bytes(webp_bytes([art(1), art(2)], lossless=True))
    assert main.is_animation(str(anim)) and not main.is_animation(str(still))
    assert main.is_animation("x.gif") and not main.is_animation("x.png")


def test_the_command_line_cleans_up_a_lossy_webp(tmp_path, capsys):
    import convert_cli
    sheet = Image.new("RGBA", (300, 120), (30, 60, 30, 255))
    for i in range(4):
        sheet.paste(art(i).resize((64, 48), Image.NEAREST), (8 + i * 72, 30))
    p = tmp_path / "sheet.webp"
    p.write_bytes(webp_bytes([sheet], quality=80))
    assert convert_cli.main([str(p), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "Lossy WebP" in out and "cleaned up to" in out
    assert list((tmp_path / "out").glob("sheet_RSR_*.png"))


def test_pop_up_messages_use_the_dark_theme():
    """A message box opened from a window has the dark panel colour behind light text (not white behind grey)."""
    from PySide6.QtGui import QPalette
    from src.app.gif_window import GifWindow
    from src.app.theme import PANEL
    from tests.test_window import _APP
    w = GifWindow()
    w.show()
    box = QMessageBox(QMessageBox.Warning, "t", "Some text", QMessageBox.Ok, w)
    box.show()
    _APP.processEvents()
    img = box.grab().toImage()
    c = img.pixelColor(img.width() - 5, img.height() // 2)
    assert c.lightness() < 80                                   # dark, not the system white
    assert box.palette().color(QPalette.WindowText).lightness() > 180
    box.close()
    box.deleteLater()
    w.close()
    w.deleteLater()


def test_there_are_seven_strengths_in_even_steps():
    names = list(colours.STRENGTHS)
    assert names == ["Very low", "Low", "Medium-low", "Medium", "Medium-high", "High", "Very high"]
    assert [colours.STRENGTHS[n] for n in names] == [16, 24, 32, 40, 48, 56, 64]       # Low, Medium, High unchanged
    assert colours.DEFAULT_STRENGTH == "Medium"
    assert colours.strength_from_text("medium-high") == "Medium-high"
    assert colours.strength_from_text("Very low") == colours.strength_from_text("very_low") == "Very low"
    assert colours.strength_from_text("extreme") is None


def test_each_step_up_merges_at_least_as_much_on_the_whole():
    f = rgba(webp_bytes([art(3)], quality=60))
    after = [colours.clean_up([f], s).after for s in colours.STRENGTHS]
    assert after[0] > after[-1]
    assert all(a <= min(after[:i]) + 1 for i, a in enumerate(after) if i)    # a step may keep one more, no more


def test_the_window_lists_all_seven_strengths():
    from PySide6.QtWidgets import QApplication
    from src.app.cleanup_controls import CleanupControls
    QApplication.instance() or QApplication([])
    c = CleanupControls()
    assert [c.strength.itemText(i) for i in range(c.strength.count())] == list(colours.STRENGTHS)
    assert c.strength.currentData() == "Medium"


def test_the_command_line_takes_the_new_strength_names(tmp_path, capsys):
    import convert_cli
    sheet = Image.new("RGBA", (300, 120), (30, 60, 30, 255))
    for i in range(4):
        sheet.paste(art(i).resize((64, 48), Image.NEAREST), (8 + i * 72, 30))
    p = tmp_path / "sheet.webp"
    p.write_bytes(webp_bytes([sheet], quality=80))
    assert convert_cli.main([str(p), "--out", str(tmp_path / "out"), "--clean", "medium-high"]) == 0
    assert "(Medium-high)" in capsys.readouterr().out
