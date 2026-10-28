"""Pixel art enlarged by a fraction (such as 2.5x or 6.67x), and frames that are too big to use. Only made-up pictures."""
import io

import numpy as np
import pytest
from PIL import Image

from src.core import gif
from tests.test_webp import art, webp_bytes


def gif_of(frames) -> Image.Image:
    b = io.BytesIO()
    frames[0].save(b, "GIF", save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
    b.seek(0)
    return Image.open(b)


SMALL = [art(s, scale=1).convert("RGB") for s in (1, 2, 3)]          # the real pictures: 64 x 48
TRUTH = [np.asarray(f) for f in SMALL]


def enlarged(ratio):
    size = (round(64 * ratio), round(48 * ratio))
    return [f.resize(size, Image.NEAREST) for f in SMALL], size


@pytest.mark.parametrize("ratio", [1.75, 2.5, 3.5, 4.2, 6.67])
def test_a_fractional_enlargement_is_reduced_exactly(ratio):
    frames, size = enlarged(ratio)
    s = gif.read_gif(gif_of(frames))
    assert s.scale.grid == (64, 48) and s.scale.match == 1.0 and s.reduce_default
    assert s.size == (64, 48) and s.grid_used == (64, 48) and not s.error
    assert all(np.array_equal(f.rgba[..., :3], t) for f, t in zip(s.frames, TRUTH))     # every pixel is right
    assert gif.ratio_text(size[0] / 64) in s.note and "enlargement of 64 x 48" in s.note


def test_a_lossy_fractional_webp_is_cleaned_then_reduced():
    frames, size = enlarged(3.5)
    data = webp_bytes([f.convert("RGBA") for f in frames], quality=85, duration=80)
    s = gif.read_gif(Image.open(io.BytesIO(data)), lossy=True)
    assert s.scale.grid == (64, 48) and s.size == (64, 48) and s.scale.match >= gif.WEAK_MATCH
    off = [np.sqrt(((f.rgba[..., :3].astype(int) - t.astype(int)) ** 2).sum(-1)) for f, t in zip(s.frames, TRUTH)]
    visibly_wrong = sum(int((d > 40).sum()) for d in off)               # a shade off is fine after lossy compression
    assert visibly_wrong < 0.005 * 64 * 48 * 3


def test_a_one_to_one_picture_is_not_taken_for_a_fractional_enlargement():
    rng = np.random.default_rng(3)
    a = np.zeros((60, 80, 3), np.uint8)
    a[:] = (30, 60, 30)
    for _ in range(40):
        x, y = rng.integers(0, 75), rng.integers(0, 55)
        a[y:y + rng.integers(1, 6), x:x + rng.integers(1, 6)] = rng.integers(0, 255, 3)
    s = gif.read_gif(gif_of([Image.fromarray(a), Image.fromarray(np.roll(a, 3, 1))]))
    assert not s.scale.found and s.size == (80, 60)


def test_too_few_edges_are_not_enough_to_guess_a_fraction():
    from tests.test_gif import blob, make_gif, _frames
    small = _frames(make_gif([blob(2, 2), blob(6, 3), blob(10, 4)], size=(20, 16)))
    s = gif.read_gif(gif_of([f.resize((50, 40), Image.NEAREST) for f in small]))
    assert s.scale.grid is None and s.size == (50, 40)


def test_a_detected_size_can_be_chosen_by_hand():
    frames, _ = enlarged(3.5)
    s = gif.read_gif(gif_of(frames), reduce=False)
    assert s.size == (224, 168) and s.too_big and "looks like a 3.5x enlargement" in s.note
    assert len(s.frames) == 3                                           # shown, though too big to use
    gif.apply_scale(s, False, ("grid", 64, 48))
    assert s.size == (64, 48) and not s.error and not s.too_big


def test_too_big_frames_are_kept_for_showing_but_nothing_is_built():
    big = Image.new("RGB", (200, 60), (20, 20, 20))
    for x in range(0, 200, 3):
        big.putpixel((x, x % 60), (200, 50, 50))
    s = gif.read_gif(gif_of([big, big.rotate(180)]))
    assert s.too_big and s.error.startswith("Frames are 200 x 60") and len(s.frames) == 2
    r = gif.build(s, gif.GifOptions())
    assert r.analysis is None and r.message == s.error


def test_the_session_says_what_to_do():
    from src.app.gif_session import GifSession
    frames, _ = enlarged(3.5)
    sess = GifSession(gif_of(frames))
    assert sess.found and sess.grid_choice() == ("64 x 48 (3.5x)", ("grid", 64, 48))
    assert sess.problem_text() == ""
    sess.set_scaling(False, None)
    assert "Tick Reduce to real pixel size" in sess.problem_text()
    sess.set_scaling(True, 1)
    assert "Choose Auto in Pixel size" in sess.problem_text()


def sprite(seed, transparent=True) -> Image.Image:
    """A made-up 42 x 42 figure with busy shading (many small colour patches), on a transparent or plain background."""
    rng = np.random.default_rng(seed)
    pal = rng.integers(20, 235, (12, 3))
    a = np.zeros((42, 42, 4), np.uint8)
    a[..., :3], a[..., 3] = (240, 240, 240), 0 if transparent else 255
    yy, xx = np.mgrid[:42, :42]
    body = ((xx - 21) / 13.0) ** 2 + ((yy - 21) / 18.0) ** 2 <= 1
    body |= (abs(xx - 21 + rng.integers(-3, 4)) < 4) & (yy > 30) & (yy < 41)       # legs
    body |= (abs(yy - 16) < 3) & (xx > 4) & (xx < 38)                               # arms
    shade = np.zeros((42, 42, 3), np.int64)
    shade[:] = pal[0]
    for _ in range(160):                                                            # patches of 1 to 4 pixels each way
        x, y, w, h = *rng.integers(0, 42, 2), *rng.integers(1, 5, 2)
        shade[y:y + h, x:x + w] = pal[rng.integers(0, 12)]
    a[body, :3], a[body, 3] = shade[body], 255
    return Image.fromarray(a)


MARIO_LIKE = 200                                                         # 42 pixels shown as 200: a 4.76x enlargement


@pytest.mark.parametrize("transparent, quality", [(True, 30), (False, 75)])
def test_a_lossy_webp_enlarged_476_times_is_found(transparent, quality):
    """Like a sprite saved from a web page: lossy compression smudges the colours, so few colour changes sit exactly
    on the grid. The outline against transparency stays crisp (at quality 30 the colours alone show no grid at all);
    without transparency, at milder compression, the grid still stands out from every other size."""
    small = [sprite(s, transparent) for s in (1, 2, 3)]
    big = [f.resize((MARIO_LIKE, MARIO_LIKE), Image.NEAREST) for f in small]
    s = gif.read_gif(Image.open(io.BytesIO(webp_bytes(big, quality=quality, duration=80))), lossy=True)
    assert s.scale.grid == (42, 42) and s.size == (42, 42) and not s.too_big and not s.error
    assert s.scale.match >= gif.WEAK_MATCH and len(s.frames) == 3


def test_a_lossy_one_to_one_sprite_is_left_alone():
    s = gif.read_gif(Image.open(io.BytesIO(webp_bytes([sprite(4), sprite(5)], quality=75))), lossy=True)
    assert not s.scale.found and s.size == (42, 42)
