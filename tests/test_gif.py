"""Reading animated GIFs into frames and a size group (PRD section 10)."""
import io

import numpy as np
from PIL import Image

from src.core import gif, output
from src.core.detect import Options
from src.core.gif import GifOptions


def make_gif(frames, size=(20, 16), transparency=None, disposal=2, duration=50):
    """frames: list of dicts {(x, y): (r, g, b)} drawn on a palette-less RGB picture of one background colour."""
    imgs = []
    for pts in frames:
        im = Image.new("RGB", size, (30, 60, 30))
        for (x, y), c in pts.items():
            im.putpixel((x, y), c)
        imgs.append(im.convert("P", palette=Image.ADAPTIVE, colors=64))
    buf = io.BytesIO()
    kw = dict(save_all=True, append_images=imgs[1:], duration=duration, loop=0, disposal=disposal)
    imgs[0].save(buf, "GIF", **kw)
    buf.seek(0)
    return Image.open(buf)


def blob(x, y, c=(200, 40, 40), n=3):
    return {(x + i, y + j): c for i in range(n) for j in range(n)}


RED, BLUE = (200, 40, 40), (40, 40, 200)


def test_reads_every_frame_as_a_full_picture():
    g = make_gif([blob(2, 2), blob(6, 3), blob(10, 4)])
    s = gif.read_gif(g)
    assert not s.error and len(s.frames) == 3 and s.size == (20, 16)
    assert s.frames[1].rgba.shape == (16, 20, 4)
    assert tuple(s.frames[1].rgba[4, 7, :3]) != tuple(s.frames[1].rgba[0, 0, :3])      # the blob is there, whole


def test_background_is_the_commonest_border_colour():
    s = gif.read_gif(make_gif([blob(2, 2), blob(6, 3)]))
    bg = gif.detect_background(s)
    assert bg == int(s.frames[0].key[0, 0])


def sheet_of(blobs, size=(20, 16)):
    """A GifSheet built directly (the GIF writer itself merges identical frames, so it cannot make repeats)."""
    frames = []
    for i, pts in enumerate(blobs):
        key = np.full((size[1], size[0]), 0x1E3C1E, np.int32)
        for (x, y), c in pts.items():
            key[y, x] = (c[0] << 16) | (c[1] << 8) | c[2]
        rgba = np.zeros((size[1], size[0], 4), np.uint8)
        frames.append(gif.GifFrame(i, rgba, key))
    gif.mark_repeats(frames)
    return gif.GifSheet(size, frames)


def test_repeated_frames_are_marked_and_dropped():
    s = sheet_of([blob(2, 2), blob(2, 2), blob(6, 3), blob(6, 3), blob(6, 3), blob(2, 2)])
    assert [f.repeat for f in s.frames] == [False, True, False, True, True, False]
    r = gif.build(s, GifOptions())
    assert len(r.kept) == 3 and r.repeats_dropped == 3
    r2 = gif.build(s, GifOptions(remove_repeats=False))
    assert len(r2.kept) == 6 and r2.repeats_dropped == 0


def test_the_user_can_keep_a_repeat_and_drop_another_frame():
    s = sheet_of([blob(2, 2), blob(2, 2), blob(6, 3)])
    r = gif.build(s, GifOptions(), toggled={1, 2})            # keep the repeat (1), drop frame 2
    assert [f.index for f in r.kept] == [0, 1]


def test_trim_makes_the_box_the_area_that_moves():
    s = gif.read_gif(make_gif([blob(2, 2), blob(6, 5)]))
    r = gif.build(s, GifOptions(trim=True))
    assert r.box == (2, 2, 8, 7)                              # union of both blobs
    g = r.groups[0]
    assert (g.width, g.height) == (7, 6) and g.count == 2 and not g.problem
    whole = gif.build(s, GifOptions(trim=False))
    assert whole.box == (0, 0, 19, 15) and (whole.groups[0].width, whole.groups[0].height) == (20, 16)


def test_a_sprite_keeps_its_place_from_frame_to_frame():
    s = gif.read_gif(make_gif([blob(2, 2), blob(6, 5)]))
    r = gif.build(s, GifOptions())
    res = output.build_sheets(r.analysis, r.groups, "runner", Options())
    sheet = res.sheets[0]
    assert sheet.file_name == "runner_RSR_7x6.png" and sheet.count == 2
    img = np.asarray(sheet.image.convert("RGB"))
    # frame 1 starts at x=1, y=62+1; the blob is at (0,0) inside it, frame 2's blob at (4,3) inside its frame
    f1 = img[63:69, 1:8]
    f2 = img[63:69, 9:16]
    assert tuple(f1[0, 0]) != (255, 0, 255) and tuple(f1[5, 6]) == (255, 0, 255)
    assert tuple(f2[3, 4]) != (255, 0, 255) and tuple(f2[0, 0]) == (255, 0, 255)


def test_the_background_becomes_transparent_magenta_and_can_be_picked():
    s = gif.read_gif(make_gif([blob(2, 2), blob(6, 5)]))
    red_key = int(s.frames[0].key[3, 3])
    r = gif.build(s, GifOptions(background=red_key))           # picking the sprite colour as background
    assert r.background == red_key
    assert r.box is not None                                   # the old background now counts as sprite


def test_a_gif_over_128_pixels_is_refused_and_nothing_is_scaled():
    big = Image.new("P", (129, 20))
    buf = io.BytesIO()
    big.save(buf, "GIF")
    buf.seek(0)
    s = gif.read_gif(Image.open(buf))
    assert s.error == "Frames are 129 x 20. Sprite sizes must be 4 to 128 pixels." and not s.frames
    assert gif.build(s, GifOptions()).message == s.error


def test_a_gif_under_4_pixels_is_refused():
    tiny = Image.new("P", (3, 3))
    buf = io.BytesIO()
    tiny.save(buf, "GIF")
    buf.seek(0)
    assert "4 to 128" in gif.read_gif(Image.open(buf)).error


def test_all_background_says_no_sprites_found():
    s = gif.read_gif(make_gif([{}, {}]))
    assert gif.build(s, GifOptions()).message == "No sprites were found. Check the background colour."


def test_a_trimmed_box_under_4_pixels_is_refused_by_the_group():
    s = gif.read_gif(make_gif([blob(2, 2, n=2), blob(2, 2, n=2)], size=(20, 16)))
    r = gif.build(s, GifOptions())
    assert r.groups[0].problem.startswith("Frames are 2 x 2.")
    assert output.build_sheets(r.analysis, r.groups, "x", Options()).refused


def test_over_120_frames_split_into_sheets():
    frames = [blob(i % 14, i % 10, c=(10 + i % 200, 40, 40)) for i in range(130)]
    s = gif.read_gif(make_gif(frames))
    r = gif.build(s, GifOptions(remove_repeats=False))
    res = output.build_sheets(r.analysis, r.groups, "big", Options())
    assert [x.count for x in res.sheets] == [120, 10]
    assert res.sheets[1].file_name.startswith("big_RSR_part2_")


def test_transparent_gif_uses_transparency_as_background():
    imgs = []
    for x in (2, 8):
        im = Image.new("RGBA", (20, 16), (0, 0, 0, 0))
        for i in range(3):
            for j in range(3):
                im.putpixel((x + i, 4 + j), (200, 40, 40, 255))
        imgs.append(im)
    buf = io.BytesIO()
    imgs[0].save(buf, "GIF", save_all=True, append_images=imgs[1:], duration=50, loop=0, disposal=2, transparency=0)
    buf.seek(0)
    s = gif.read_gif(Image.open(buf))
    assert s.had_alpha and gif.detect_background(s) == -1
    assert gif.build(s, GifOptions()).box == (2, 4, 10, 6)


def enlarged(factor, frames=((2, 2), (6, 3), (10, 4)), size=(20, 16)):
    """A GIF whose every pixel is drawn as factor x factor pixels."""
    small = make_gif([blob(x, y) for x, y in frames], size=size)
    out = []
    for i in range(len(frames)):
        small.seek(i)
        out.append(small.convert("RGB").resize((size[0] * factor, size[1] * factor), Image.NEAREST))
    buf = io.BytesIO()
    out[0].save(buf, "GIF", save_all=True, append_images=out[1:], duration=50, loop=0, disposal=2)
    buf.seek(0)
    return Image.open(buf)


def test_a_gif_that_is_an_exact_enlargement_is_reduced_to_its_real_size():
    s = gif.read_gif(enlarged(8, size=(20, 16)))                      # 160 x 128: too big as it stands
    assert not s.error and s.size == (20, 16) and len(s.frames) == 3
    assert s.frames[0].rgba.shape == (16, 20, 4)
    assert "exact 8x enlargement" in s.note and "160 x 128" in s.note and "20 x 16" in s.note
    plain = gif.read_gif(make_gif([blob(2, 2), blob(6, 3), blob(10, 4)]))
    assert all(np.array_equal(a.key, b.key) for a, b in zip(s.frames, plain.frames))          # nothing was lost


def test_the_largest_whole_number_is_used():
    s = gif.read_gif(enlarged(4, size=(40, 32)))                      # 160 x 128, drawn at 4x of 40 x 32
    assert s.size == (40, 32) and "exact 4x" in s.note


def test_an_enlarged_gif_that_is_still_too_big_underneath_is_refused():
    s = gif.read_gif(enlarged(2, size=(130, 40)))                     # 260 x 80: underneath it is 130 wide
    assert s.error and "260 x 80" in s.error and "4 to 128" in s.error and not s.frames


def _gif_of(frames):
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
    buf.seek(0)
    return Image.open(buf)


def _frames(im, n=3):
    out = []
    for i in range(n):
        im.seek(i)
        out.append(im.convert("RGB"))
    return out


def test_a_big_gif_with_a_stray_pixel_is_still_reduced_with_its_match_shown():
    frames = _frames(enlarged(8, size=(20, 16)))
    frames[1].putpixel((5 * 8 + 3, 3 * 8 + 3), (1, 2, 3))                     # one pixel breaks an 8 x 8 block
    s = gif.read_gif(_gif_of(frames))
    assert not s.error and s.size == (20, 16) and s.factor == 8
    assert "% of sprite pixels match" in s.note and "exact" not in s.note
    plain = gif.read_gif(make_gif([blob(2, 2), blob(6, 3), blob(10, 4)]))
    assert all(np.array_equal(a.key, b.key) for a, b in zip(s.frames, plain.frames))     # the stray pixel is outvoted


def test_a_big_gif_that_is_not_an_enlargement_is_still_refused():
    rng = np.random.default_rng(1)
    noise = [Image.fromarray(rng.integers(0, 255, (128, 160, 3), dtype=np.uint8), "RGB") for _ in range(2)]
    s = gif.read_gif(_gif_of(noise))
    assert s.error == "Frames are 160 x 128. Sprite sizes must be 4 to 128 pixels." and not s.frames
    assert s.scale.factor == 1


def test_a_blocky_gif_within_the_limit_is_reduced_by_default_and_can_be_kept():
    s = gif.read_gif(enlarged(2, size=(20, 16)))                      # 40 x 32: an exact 2x of 20 x 16
    assert s.reduce_default and s.size == (20, 16) and "exact 2x" in s.note
    kept = gif.read_gif(enlarged(2, size=(20, 16)), reduce=False)     # the switch turned off: 1:1
    assert kept.size == (40, 32) and "looks like a 2x enlargement" in kept.note


def test_an_offset_grid_and_a_plain_border_are_found():
    small = _frames(make_gif([blob(x, y) for x, y in ((2, 2), (6, 3), (10, 4))], size=(20, 16)))
    big = []
    for f in small:
        e = f.resize((60, 48), Image.NEAREST)                              # 3x
        canvas = Image.new("RGB", (62, 49), f.getpixel((0, 0)))           # a plain 2 px / 1 px margin
        canvas.paste(e, (2, 1))
        big.append(canvas)
    s = gif.read_gif(_gif_of(big))
    assert s.factor == 3 and s.scale.phase == (2, 1)
    plain = gif.read_gif(make_gif([blob(2, 2), blob(6, 3), blob(10, 4)]))
    assert s.size == (20, 16)
    assert all(np.array_equal(a.key, b.key) for a, b in zip(s.frames, plain.frames))


def test_a_part_block_with_sprite_pixels_becomes_a_whole_pixel():
    f = Image.new("RGB", (20, 16), (30, 60, 30))
    for y in range(4, 10):
        f.putpixel((0, y), (200, 40, 40))                                 # sprite pixels in the first column
    for x, y in ((4, 4), (8, 6), (12, 8), (16, 10)):
        for i in range(2):
            for j in range(2):
                f.putpixel((x + i, y + j), (40, 40, 200))
    frames = []
    for dx in (0, 2):
        g = Image.new("RGB", (20, 16), (30, 60, 30))
        g.paste(f, (0, 0))
        for i in range(2):
            for j in range(2):
                g.putpixel((10 + dx + i, 12 + j), (40, 200, 40))
        e = g.resize((40, 32), Image.NEAREST).crop((1, 0, 40, 32))      # the left column is cut to half a block
        frames.append(e)
    s = gif.read_gif(_gif_of(frames))
    assert s.factor == 2 and s.size == (20, 16)
    assert int(s.frames[0].key[5, 0]) == (200 << 16) | (40 << 8) | 40   # the half block kept its sprite colour


def test_colours_are_never_mixed_when_reducing():
    frames = _frames(enlarged(4, size=(20, 16)))
    for f in frames:
        f.putpixel((9, 9), (250, 250, 0))                                 # a stray colour inside a block
    s = gif.read_gif(_gif_of(frames))
    allowed = set()
    for f in frames:
        a = np.asarray(f).astype(np.int64)
        allowed |= set(((a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]).ravel().tolist())
    for fr in s.frames:
        assert set(np.unique(fr.key).tolist()) <= allowed
        assert (250 << 16) | (250 << 8) not in set(np.unique(fr.key).tolist())


def test_a_chosen_pixel_size_overrides_auto():
    s = gif.read_gif(enlarged(4, size=(20, 16)))                      # detected 4x
    assert s.factor == 4 and s.size == (20, 16)
    gif.apply_scale(s, True, 2)                                       # chosen by hand
    assert s.factor == 2 and s.size == (40, 32) and "exact 2x" in s.note
    gif.apply_scale(s, True, 1)
    assert s.factor == 1 and s.size == (80, 64)


def test_a_fractional_enlargement_is_not_taken_for_a_whole_one():
    small = _frames(make_gif([blob(2, 2), blob(6, 3), blob(10, 4)], size=(20, 16)))
    big = [f.resize((50, 40), Image.NEAREST) for f in small]           # 2.5x
    s = gif.read_gif(_gif_of(big))
    assert s.factor == 1 and s.size == (50, 40)
    gif.apply_scale(s, True, 2)                                       # forced by hand: warned, not refused
    assert "may not really be a 2x enlargement" in s.note


def test_a_few_plain_squares_are_never_mistaken_for_an_enlargement():
    s = gif.read_gif(make_gif([blob(2, 2, n=2), blob(4, 4, n=2)], size=(20, 16)))
    assert s.scale.factor == 1 and s.size == (20, 16) and not s.note


def test_the_owners_enlarged_gif_becomes_64_x_80():
    from pathlib import Path
    s = gif.read_gif(Image.open(Path(__file__).parent / "samples" / "enlarged_4x_character.gif"))     # 256 x 320, 4x
    assert not s.error and s.size == (64, 80) and len(s.frames) == 6
    r = gif.build(s, GifOptions())
    assert r.analysis is not None and r.box is not None
    res = output.build_sheets(r.analysis, r.groups, "character", Options())
    assert len(res.sheets) == 1 and not res.refused
