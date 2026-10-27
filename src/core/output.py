"""Writing the RunSpriteRun boxed sprite sheets (PRD section 6). Builds the pictures and the messages; no file or
screen code here."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .detect import Analysis, Options, Shape
from .layout import SizeGroup, sheet_parts

PER_ROW = 10
BAR_H = 62
MARGIN = 6
LINE_H = 11
MIN_WIDTH = 640
GREY = (224, 224, 224)
TEXT = (0, 0, 0)
TRANSPARENT = (255, 0, 255)
NEAR_TRANSPARENT = (254, 0, 255)
SWATCH = 8
SWATCH_GAP = 4
MAX_SWATCHES = 256              # a sheet with more colours than this has no colour bar beyond the first 256
BOX_CANDIDATES = ((0, 255, 0), (0, 255, 255), (255, 255, 0), (0, 0, 255), (255, 0, 0), (0, 128, 255), (255, 128, 0),
                  (128, 255, 0), (0, 255, 128), (128, 0, 255), (255, 0, 128))


@dataclass
class OutputSheet:
    file_name: str
    image: Image.Image
    width: int                 # frame size
    height: int
    count: int                 # frames on this sheet
    part: int = 1
    colours: int = 0
    box_colour: tuple = (0, 255, 0)
    messages: list[str] = field(default_factory=list)       # orange messages about this sheet
    save: bool = True


@dataclass
class Result:
    sheets: list[OutputSheet] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)        # size groups that could not be written, and why
    messages: list[str] = field(default_factory=list)       # for the whole file (partly transparent pixels)


def sheet_file_name(stem: str, w: int, h: int, part: int) -> str:
    return f"{stem}_RSR_{w}x{h}.png" if part == 1 else f"{stem}_RSR_part{part}_{w}x{h}.png"


def frame_pixels(analysis: Analysis, shape: Shape, w: int, h: int, vertical: str):
    """The frame as a (h, w, 3) uint8 array, the picture is placed centred, with its feet on the bottom edge (or
    centred up and down). Everything that is not sprite is the transparent colour. Returns (array, changed) where
    `changed` is how many sprite pixels that were exactly the transparent colour had to be nudged."""
    out = np.empty((h, w, 3), np.uint8)
    out[:] = TRANSPARENT
    x0, y0, x1, y1 = shape.box
    sw, sh = x1 - x0 + 1, y1 - y0 + 1
    key = analysis.key[y0:y1 + 1, x0:x1 + 1]
    rgb = np.stack([(key >> 16) & 255, (key >> 8) & 255, key & 255], axis=-1).astype(np.uint8)
    mask = shape.mask & (key >= 0)
    clash = mask & (rgb[..., 0] == 255) & (rgb[..., 1] == 0) & (rgb[..., 2] == 255)
    rgb[clash] = NEAR_TRANSPARENT
    ox = (w - sw) // 2
    oy = (h - sh) if vertical == "bottom" else (h - sh) // 2
    region = out[oy:oy + sh, ox:ox + sw]
    region[mask] = rgb[mask]
    return out, int(clash.sum())


def box_colour(used: set[tuple]) -> tuple:
    taken = set(used) | {TRANSPARENT}
    for c in BOX_CANDIDATES:
        if c not in taken:
            return c
    for v in range(255, -1, -1):
        if (0, v, 255 - v) not in taken:
            return (0, v, 255 - v)
    return (0, 255, 0)


def sheet_size(w: int, h: int, count: int, colours: int) -> tuple[int, int, int, int]:
    per = max(1, min(PER_ROW, count))
    rows = max(1, math.ceil(count / per))
    width = max(MIN_WIDTH, per * (w + 1) + 1)
    grid_h = rows * (h + 1) + 1
    colours = min(colours, MAX_SWATCHES)
    swatches_per_row = max(1, (width + SWATCH_GAP) // (SWATCH + SWATCH_GAP))
    bar_rows = max(1, math.ceil(colours / swatches_per_row))
    total_h = BAR_H + grid_h + SWATCH_GAP + bar_rows * SWATCH + (bar_rows - 1) * SWATCH_GAP
    return width, total_h, per, rows


def text_lines(w: int, h: int, per: int, rows: int, count: int, colours: int, box: tuple, source: str) -> list[str]:
    hexs = lambda c: "#%02X%02X%02X" % tuple(c)
    return [
        f"RunSpriteRun sheet converter   Source: {source}",
        f"Colours are kept exactly as in the source: {colours} colours used, including the transparent colour.",
        "RunSpriteRun checks the colours for your system when you import this sheet.",
        f"Sprites: {w} x {h} pixels, {per} per row, {rows} rows ({count} sprites).",
        f"The {hexs(box)} lines are guides: do not use that colour in the sprites. Transparent colour is "
        f"{hexs(TRANSPARENT)}.",
    ]


def _build_image(frames: list[np.ndarray], w: int, h: int, palette: list[tuple], box: tuple,
                 source: str) -> Image.Image:
    count = len(frames)
    width, height, per, rows = sheet_size(w, h, count, len(palette))
    img = Image.new("RGB", (width, height), GREY)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=10)
    for n, line in enumerate(text_lines(w, h, per, rows, count, len(palette), box, source)):
        draw.text((MARGIN, MARGIN - 2 + n * LINE_H), line, fill=TEXT, font=font)
    grid_w, grid_h = per * (w + 1) + 1, rows * (h + 1) + 1
    draw.rectangle((0, BAR_H, grid_w - 1, BAR_H + grid_h - 1), fill=box)
    for n in range(per * rows):                              # every box is drawn, empty ones in the transparent colour
        x, y = 1 + (n % per) * (w + 1), BAR_H + 1 + (n // per) * (h + 1)
        draw.rectangle((x, y, x + w - 1, y + h - 1), fill=TRANSPARENT)
        if n < len(frames):
            img.paste(Image.fromarray(frames[n], "RGB"), (x, y))
    per_bar = max(1, (width + SWATCH_GAP) // (SWATCH + SWATCH_GAP))
    bar_y = BAR_H + grid_h + SWATCH_GAP
    for n, colour in enumerate(palette[:MAX_SWATCHES]):
        x = (n % per_bar) * (SWATCH + SWATCH_GAP)
        y = bar_y + (n // per_bar) * (SWATCH + SWATCH_GAP)
        img.paste(Image.new("RGB", (SWATCH, SWATCH), colour), (x, y))
    return img


def build_sheets(analysis: Analysis, groups: list[SizeGroup], stem: str, opts: Options) -> Result:
    """One sheet for each size group (more if there are over 120 frames). Nothing is written to disk."""
    res = Result()
    if analysis.partial_alpha:
        res.messages.append(f"{analysis.partial_alpha:,} pixels were partly transparent and have been made solid or "
                            f"transparent.")
    for g in groups:
        if g.problem:
            res.refused.append(g.problem)
            continue
        parts = sheet_parts(g)
        if len(parts) > 1:
            res.messages.append(f"{g.count} sprites of size {g.width} x {g.height} do not fit on one sheet, so they "
                                f"are split into {len(parts)} sheets.")
        for part_no, shapes in enumerate(parts, 1):
            frames, changed = [], 0
            for s in shapes:
                arr, c = frame_pixels(analysis, s, g.width, g.height, opts.vertical)
                frames.append(arr)
                changed += c
            flat = np.concatenate([f.reshape(-1, 3) for f in frames])
            used = np.unique(flat, axis=0)
            palette = [tuple(int(v) for v in c) for c in used]
            box = box_colour(set(palette))
            msgs = []
            if changed:
                msgs.append(f"{changed} sprite pixels were exactly (255, 0, 255) and were changed to (254, 0, 255).")
            img = _build_image(frames, g.width, g.height, palette, box, stem)
            res.sheets.append(OutputSheet(sheet_file_name(stem, g.width, g.height, part_no), img, g.width, g.height,
                                          len(frames), part_no, len(palette), box, msgs))
    return res
