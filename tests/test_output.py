import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from src.core import layout, output
from src.core.detect import Options, analyse
from tests.helpers import PALETTE, blank, make_sprite, opaque_set, paste

RSR_HOME = Path("/home/claude/RunSpriteRun_experimental")


def convert(sheet, opts=None, stem="knight"):
    opts = opts or Options()
    a = analyse(sheet, opts)
    groups = layout.make_groups(a, opts)
    return a, groups, output.build_sheets(a, groups, stem, opts)


def find_boxes(img, box):
    """The frames in a sheet, found the way RunSpriteRun does: the spaces between lines of the box colour."""
    rgb = np.asarray(img.convert("RGB")).astype(int)
    hit = (rgb == np.array(box)).all(axis=2)
    xr = _runs([x for x in range(hit.shape[1]) if _long(hit[:, x])])
    yr = _runs([y for y in range(hit.shape[0]) if _long(hit[y, :])])
    return [(x0[1] + 1, y0[1] + 1, x1[0] - 1, y1[0] - 1) for y0, y1 in zip(yr, yr[1:]) for x0, x1 in zip(xr, xr[1:])]


def _runs(values):
    """Runs of consecutive numbers as (first, last)."""
    out, start = [], None
    for i, v in enumerate(values):
        if start is None:
            start = v
        if i + 1 == len(values) or values[i + 1] != v + 1:
            out.append((start, v))
            start = None
    return out


def _long(v):
    n = 0
    for b in v:
        n = n + 1 if b else 0
        if n >= 4:
            return True
    return False


def test_frame_placement_centred_with_feet_on_the_bottom():
    sheet = blank(60, 60)
    spr = make_sprite(np.random.default_rng(1), 10, 14)
    paste(sheet, spr, 20, 20)
    a = analyse(sheet)
    arr, changed = output.frame_pixels(a, a.kept()[0], 20, 30, "bottom")
    assert arr.shape == (30, 20, 3) and changed == 0
    opaque = {(x - 5, y - 16): tuple(int(v) for v in arr[y, x]) for y in range(30) for x in range(20)
              if tuple(arr[y, x]) != output.TRANSPARENT}
    assert opaque == opaque_set(spr)                                         # x offset (20-10)//2, feet at row 29
    arr2, _ = output.frame_pixels(a, a.kept()[0], 20, 30, "centre")
    assert tuple(arr2[0, 0]) == output.TRANSPARENT
    assert {(x - 5, y - 8) for y in range(30) for x in range(20) if tuple(arr2[y, x]) != output.TRANSPARENT} \
        == set(opaque_set(spr))


def test_a_sprite_pixel_that_is_exactly_the_transparent_colour_is_nudged_and_counted():
    sheet = blank(40, 40)
    spr = make_sprite(np.random.default_rng(2), 10, 10, palette=[(255, 0, 255), (200, 30, 30)])
    paste(sheet, spr, 10, 10)
    a, groups, res = convert(sheet)
    expected = sum(1 for c in opaque_set(spr).values() if c == (255, 0, 255))
    assert expected > 0
    assert res.sheets[0].messages[0].startswith(f"{expected} sprite pixels were exactly (255, 0, 255)")
    # no pixel inside the boxes is a sprite pixel with the transparent colour any more
    boxes = find_boxes(res.sheets[0].image, res.sheets[0].box_colour)
    x0, y0, x1, y1 = boxes[0]
    got = np.asarray(res.sheets[0].image.convert("RGB"))[y0:y1 + 1, x0:x1 + 1]
    n_nudged = int((got == (254, 0, 255)).all(axis=2).sum())
    assert n_nudged == expected


def test_scrambled_layout_round_trip_matches_pixel_for_pixel():
    rng = np.random.default_rng(3)
    sizes = [(14, 20), (18, 24), (12, 22), (16, 16), (20, 26), (10, 18)]
    sprites = [make_sprite(rng, w, h) for w, h in sizes]
    sheet = blank(300, 220, bg=(12, 90, 40))                        # a different background and layout each time
    spots = [(7, 9), (70, 15), (140, 8), (20, 100), (95, 110), (200, 105)]
    for s, (x, y) in zip(sprites, spots):
        paste(sheet, s, x, y)
    a, groups, res = convert(sheet, Options(size_tolerance=32))
    assert len(res.sheets) == 1 and res.sheets[0].count == 6
    out = res.sheets[0]
    boxes = find_boxes(out.image, out.box_colour)
    assert len(boxes) >= 6
    w, h = groups[0].width, groups[0].height
    rgb = np.asarray(out.image.convert("RGB"))
    # reading order of the source: row by row (top row first), left to right
    order = sorted(range(6), key=lambda i: (spots[i][1] + sizes[i][1] > 60, spots[i][0]))
    for n, i in enumerate(order):
        x0, y0, x1, y1 = boxes[n]
        assert (x1 - x0 + 1, y1 - y0 + 1) == (w, h)
        frame = rgb[y0:y1 + 1, x0:x1 + 1]
        solid = ~(frame == np.array(output.TRANSPARENT)).all(axis=2)
        ys, xs = np.nonzero(solid)
        found = {(int(x - xs.min()), int(y - ys.min())): tuple(int(v) for v in frame[y, x]) for y, x in zip(ys, xs)}
        assert found == opaque_set(sprites[i])


def test_sheet_names_and_split_over_120():
    rng = np.random.default_rng(4)
    sheet = blank(14 * 13 + 20, 16 * 10 + 20)
    for r in range(10):
        for c in range(13):
            paste(sheet, make_sprite(rng, 8, 8), 10 + c * 14, 10 + r * 16)
    a, groups, res = convert(sheet, stem="hero")
    assert [(s.file_name, s.count) for s in res.sheets] == [("hero_RSR_8x8.png", 120), ("hero_RSR_part2_8x8.png", 10)]
    assert any("130 sprites of size 8 x 8 do not fit on one sheet, so they are split into 2 sheets." in m
               for m in res.messages)
    assert res.sheets[0].image.size[0] >= 640


def test_each_size_group_is_its_own_sheet_named_with_its_size():
    rng = np.random.default_rng(5)
    sheet = blank(200, 150)
    paste(sheet, make_sprite(rng, 20, 30), 10, 10)
    paste(sheet, make_sprite(rng, 60, 40), 10, 80)
    a, groups, res = convert(sheet, Options(size_tolerance=0))
    assert [s.file_name for s in res.sheets] == ["knight_RSR_20x30.png", "knight_RSR_60x40.png"]


def test_box_colour_changes_when_a_sprite_uses_green():
    sheet = blank(40, 40)
    paste(sheet, make_sprite(np.random.default_rng(6), 10, 10, palette=[(0, 255, 0), (200, 30, 30)]), 10, 10)
    a, groups, res = convert(sheet)
    assert res.sheets[0].box_colour == (0, 255, 255)


def test_colours_are_kept_exactly_and_counted_without_any_system_limit():
    palette = [(i * 4, 30, 250 - i * 4) for i in range(52)]
    sheet = blank(60, 60)
    paste(sheet, make_sprite(np.random.default_rng(8), 40, 40, palette=palette), 10, 10)
    a, groups, res = convert(sheet)
    s = res.sheets[0]
    assert s.colours > 32
    assert not any("allows" in m for m in s.messages + res.messages)           # nothing is limited or warned about
    frame = np.asarray(s.image.convert("RGB"))
    used = {tuple(c) for c in frame.reshape(-1, 3)}
    assert {tuple(c) for c in palette}.issubset(used)                          # every source colour is still there


def test_text_bar_says_colours_are_kept():
    sheet = blank(40, 40)
    paste(sheet, make_sprite(np.random.default_rng(3), 10, 10), 10, 10)
    a, groups, res = convert(sheet)
    lines = output.text_lines(10, 10, 1, 1, 1, res.sheets[0].colours, res.sheets[0].box_colour, "knight")
    assert len(lines) == 5 and "kept exactly" in lines[1] and "Amiga" not in " ".join(lines)


def test_partly_transparent_pixels_are_made_solid_or_clear_and_counted():
    sheet = blank(30, 30, alpha=True)
    paste(sheet, make_sprite(np.random.default_rng(9), 10, 10), 5, 5)
    sheet.putpixel((5, 5), (200, 30, 30, 200))                           # alpha 200: becomes solid
    sheet.putpixel((6, 5), (200, 30, 30, 50))                            # alpha 50: becomes clear
    a, groups, res = convert(sheet)
    assert any("2 pixels were partly transparent" in m for m in res.messages)


def test_a_group_outside_the_size_limits_is_refused_and_nothing_is_written_for_it():
    sheet = blank(60, 100)
    paste(sheet, make_sprite(np.random.default_rng(10), 3, 6), 10, 10)          # 3 pixels wide: below the 4 pixel limit
    paste(sheet, make_sprite(np.random.default_rng(11), 12, 12), 10, 60)
    a, groups, res = convert(sheet, Options(size_tolerance=0))
    assert [g.problem for g in groups] == ["Frames are 3 x 6. Sprite sizes must be 4 to 128 pixels.", ""]
    assert res.refused == ["Frames are 3 x 6. Sprite sizes must be 4 to 128 pixels."]
    assert [s.file_name for s in res.sheets] == ["knight_RSR_12x12.png"]


def test_the_empty_boxes_at_the_end_of_the_last_row_are_drawn_too():
    rng = np.random.default_rng(13)
    sheet = blank(14 * 13 + 20, 40)
    for c in range(13):
        paste(sheet, make_sprite(rng, 10, 10), 10 + c * 14, 10)
    a, groups, res = convert(sheet)
    s = res.sheets[0]
    assert s.count == 13
    boxes = find_boxes(s.image, s.box_colour)
    assert len(boxes) == 20                                                   # 2 rows of 10, the last 7 empty
    rgb = np.asarray(s.image.convert("RGB"))
    x0, y0, x1, y1 = boxes[19]
    assert (rgb[y0:y1 + 1, x0:x1 + 1] == np.array(output.TRANSPARENT)).all()


@pytest.mark.skipif(not RSR_HOME.exists(), reason="RunSpriteRun source is not on this computer")
def test_runspriterun_imports_the_converted_sheet():
    rng = np.random.default_rng(12)
    sheet = blank(240, 120, bg=(0, 128, 128))
    sprites = [make_sprite(rng, 18, 24, palette=PALETTE[:5]) for _ in range(5)]
    for i, s in enumerate(sprites):
        paste(sheet, s, 10 + i * 40, 20 if i % 2 else 30)
    a, groups, res = convert(sheet, Options(size_tolerance=32), stem="test")
    out = Path("/tmp/claude_converter_roundtrip.png")
    res.sheets[0].image.save(out)
    sheet13 = blank(14 * 13 + 20, 40)
    for c in range(13):
        paste(sheet13, make_sprite(rng, 10, 10, palette=PALETTE[:5]), 10 + c * 14, 10)
    a13, g13, res13 = convert(sheet13, stem="test13")
    out13 = Path("/tmp/claude_converter_roundtrip13.png")
    res13.sheets[0].image.save(out13)
    script = (
        "import sys\nfrom PIL import Image\n"
        "from src.core.sheet_import import find_grid, import_sheet\n"
        "from src.core.systems import get_system\n"
        "im = Image.open(sys.argv[1]); box = tuple(int(v) for v in sys.argv[2].split(','))\n"
        "g = find_grid(im, box); assert not g.error, g.error\n"
        "r = import_sheet(im, 'test', g, (255, 0, 255), get_system('Amiga'))\n"
        "assert not r.rejected, r.rejected\n"
        "print(len(r.frames), g.width, g.height)\n")
    box = ",".join(str(v) for v in res.sheets[0].box_colour)
    run = subprocess.run([sys.executable, "-c", script, str(out), box], cwd=RSR_HOME, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout.split() == ["5", str(groups[0].width), str(groups[0].height)]
    box13 = ",".join(str(v) for v in res13.sheets[0].box_colour)           # a last row that is only partly filled
    run = subprocess.run([sys.executable, "-c", script, str(out13), box13], cwd=RSR_HOME, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout.split()[0] == "13"
