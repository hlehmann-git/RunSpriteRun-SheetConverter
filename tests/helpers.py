"""Pictures with known sprites on them, for the tests."""
from __future__ import annotations

import numpy as np
from PIL import Image

PALETTE = [(200, 30, 30), (30, 200, 30 + 20), (30, 30, 200), (230, 200, 40), (120, 60, 20), (240, 240, 240), (20, 20, 20)]


def make_sprite(rng: np.random.Generator, w: int, h: int, palette=PALETTE) -> np.ndarray:
    """A w x h array (h, w, 4): a solid block with random colours and a few holes inside (never on the edge, so the
    sprite is one piece and its box is exactly w x h). Alpha is 255 where the sprite is, 0 in the holes."""
    arr = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        for x in range(w):
            arr[y, x, :3] = palette[int(rng.integers(len(palette)))]
            arr[y, x, 3] = 255
    for _ in range(max(1, w * h // 40)):
        if w > 3 and h > 3:
            arr[int(rng.integers(1, h - 1)), int(rng.integers(1, w - 1)), 3] = 0
    return arr


def paste(sheet: Image.Image, sprite: np.ndarray, x: int, y: int) -> None:
    """Put the sprite's opaque pixels on the sheet at (x, y)."""
    h, w = sprite.shape[:2]
    for yy in range(h):
        for xx in range(w):
            if sprite[yy, xx, 3]:
                sheet.putpixel((x + xx, y + yy), tuple(int(v) for v in sprite[yy, xx, :3]) + (255,))


def blank(w: int, h: int, bg=(0, 128, 128), alpha: bool = False) -> Image.Image:
    return Image.new("RGBA", (w, h), (0, 0, 0, 0) if alpha else bg + (255,))


def opaque_set(sprite: np.ndarray) -> dict:
    """{(x, y): (r, g, b)} of the sprite's opaque pixels."""
    ys, xs = np.nonzero(sprite[..., 3])
    return {(int(x), int(y)): tuple(int(v) for v in sprite[y, x, :3]) for y, x in zip(ys, xs)}
