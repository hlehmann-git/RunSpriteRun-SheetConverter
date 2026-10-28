"""Sheets made by RunSpriteRun (and by this program): a grey text bar, a grid of guide-line boxes, then a colour bar.
The boxes are read as they are; the smoothed text and the colour swatches are never taken for sprites. Only made-up
pictures."""
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from src.core import layout, output
from src.core.detect import Options, analyse, find_boxed_sheet, key_of

GREY = (224, 224, 224)
MAGENTA = (255, 0, 255)


def frames_of(n, w, h, fill=MAGENTA, seed=1):
    """n made-up frames: a figure of a few colours on the fill colour, not touching every edge."""
    rng = np.random.default_rng(seed)
    pal = rng.integers(10, 245, (9, 3)).astype(np.uint8)
    out = []
    for _ in range(n):
        a = np.zeros((h, w, 3), np.uint8)
        a[:] = fill
        for _ in range(25):
            x, y = int(rng.integers(2, w - 4)), int(rng.integers(2, h - 4))
            a[y:y + int(rng.integers(1, 4)), x:x + int(rng.integers(1, 4))] = pal[rng.integers(0, 9)]
        out.append(a)
    return out


def rsr_sheet(frames, per=10, line=(0, 255, 0), fill=MAGENTA, empty_boxes=0):
    """A sheet laid out as RunSpriteRun saves one: smoothed text lines in the bar, the boxes, the colour bar."""
    h, w = frames[0].shape[:2]
    count = len(frames) + empty_boxes
    per = min(per, count)
    rows = -(-count // per)
    grid_w, grid_h = per * (w + 1) + 1, rows * (h + 1) + 1
    width = max(640, grid_w)
    colours = sorted({tuple(int(v) for v in c) for f in frames for c in f.reshape(-1, 3)})
    img = Image.new("RGB", (width, 62 + grid_h + 4 + 8 * (1 + len(colours) // 53) + 8), GREY)
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=10)                             # smoothed: many shades of grey per letter
    for n, text in enumerate(["RunSpriteRun sprite sheet: Amiga",
                              "Colour depth: 12-bit (RGB 4:4:4), 4 bits per channel (16 levels). 4,096 colours.",
                              "Palette limit: at most 32 colours in all the sprites, including the transparent colour.",
                              f"Sprites: {w} x {h} pixels, {per} per row, {rows} rows ({count} sprites).",
                              "The #00FF00 lines are guides: do not use that colour in the sprites."]):
        d.text((6, 4 + n * 11), text, fill=(0, 0, 0), font=font)
    d.rectangle((0, 62, grid_w - 1, 62 + grid_h - 1), fill=line)
    for n in range(per * rows):
        x, y = 1 + (n % per) * (w + 1), 62 + 1 + (n // per) * (h + 1)
        d.rectangle((x, y, x + w - 1, y + h - 1), fill=fill)
        if n < len(frames):
            img.paste(Image.fromarray(frames[n]), (x, y))
    for n, c in enumerate(colours):
        img.paste(Image.new("RGB", (8, 8), c), ((n % 53) * 12, 62 + grid_h + 4 + (n // 53) * 12))
    return img


def boxes_of(res_sheet):
    """The frames in an output sheet, in reading order, as arrays."""
    a = analyse(res_sheet.image)
    return [np.asarray(res_sheet.image.convert("RGB"))[s.box[1]:s.box[3] + 1, s.box[0]:s.box[2] + 1]
            for s in a.kept()]


def convert(img, opts=None):
    opts = opts or Options()
    a = analyse(img, opts)
    groups = layout.make_groups(a, opts)
    return a, output.build_sheets(a, groups, "hero", opts)


def test_the_text_already_has_many_colours():
    """Why the ordinary text test is not enough: smoothed letters are drawn in many greys."""
    img = rsr_sheet(frames_of(7, 42, 42))
    bar = np.asarray(img)[:62].reshape(-1, 3)
    assert len(np.unique(bar, axis=0)) > 20


def test_an_rsr_sheet_gives_exactly_its_frames():
    frames = frames_of(7, 42, 42)
    a, res = convert(rsr_sheet(frames))
    assert "RSR" in a.sheet_kinds and a.background == key_of(MAGENTA)
    assert len(a.kept()) == 7 and all(s.kind == "grid" and (s.width, s.height) == (42, 42) for s in a.kept())
    assert "RunSpriteRun sheet recognised: 7 sprites of 42 x 42" in a.messages[0]
    assert len(res.sheets) == 1 and res.sheets[0].count == 7 and (res.sheets[0].width, res.sheets[0].height) == (42, 42)
    assert all(np.array_equal(f, g) for f, g in zip(frames, boxes_of(res.sheets[0])))      # pixel for pixel


def test_several_rows_and_empty_boxes():
    frames = frames_of(13, 16, 24, seed=2)
    a, res = convert(rsr_sheet(frames, empty_boxes=7))                    # 2 rows of 10, the last 7 boxes empty
    assert len(a.kept()) == 13 and sum(s.reason == "empty" for s in a.shapes) == 7
    assert res.sheets[0].count == 13
    assert all(np.array_equal(f, g) for f, g in zip(frames, boxes_of(res.sheets[0])))
    a, _ = convert(rsr_sheet(frames, empty_boxes=7), Options(keep_empty=True))
    assert len(a.kept()) == 20


def test_another_line_colour_and_transparent_colour():
    """RunSpriteRun picks another guide colour when a sprite uses green, and the transparent colour can be chosen."""
    fill = (0, 0, 0)
    frames = frames_of(4, 20, 20, fill=fill, seed=3)
    a, res = convert(rsr_sheet(frames, line=(0, 255, 255), fill=fill))
    assert a.background == key_of(fill) and len(a.kept()) == 4
    out = boxes_of(res.sheets[0])
    for f, g in zip(frames, out):                                        # the black becomes the output's magenta
        see_through = (f == fill).all(-1)
        assert (g[see_through] == MAGENTA).all() and np.array_equal(g[~see_through], f[~see_through])


def test_a_sheet_made_by_this_program_converts_to_itself():
    frames = frames_of(12, 30, 18, seed=4)
    _a, first = convert(rsr_sheet(frames))
    a, again = convert(first.sheets[0].image)
    assert "RSR" in a.sheet_kinds and again.sheets[0].count == 12
    assert np.array_equal(np.asarray(first.sheets[0].image)[62:], np.asarray(again.sheets[0].image)[62:])


def test_a_sheet_with_nothing_in_its_boxes_says_so():
    img = rsr_sheet(frames_of(1, 16, 16), empty_boxes=5)
    ImageDraw.Draw(img).rectangle((1, 63, 16, 78), fill=MAGENTA)          # empty the one used box too
    a = analyse(img)
    assert "RSR" in a.sheet_kinds and not a.kept() and any("every box is empty" in m for m in a.messages)


@pytest.mark.parametrize("change", ["no bar", "uneven boxes", "chosen background"])
def test_other_sheets_go_through_the_normal_search(change):
    img = rsr_sheet(frames_of(6, 20, 20, seed=5))
    opts = Options()
    if change == "no bar":
        img = img.crop((0, 62, img.width, img.height))
    elif change == "uneven boxes":
        ImageDraw.Draw(img).line((11, 63, 11, 62 + 21), fill=(0, 255, 0))   # an extra guide line inside a box
        assert find_boxed_sheet(np.zeros((1, 1), np.int64)) is None
    else:
        opts = Options(background=key_of(GREY))                         # the user picked a colour: their choice wins
    a = analyse(img, opts)
    assert "RSR" not in a.sheet_kinds
