"""Turning an animated GIF into sprite frames (PRD section 10). Pure logic; shows nothing.

Every frame of the GIF is read as a complete picture. The frames are stacked into one tall "virtual sheet" so that the
same output code that writes sheets from a sprite sheet writes the GIF's sheet: each kept frame is one Shape whose box
is the same rectangle in every frame (so a sprite keeps its place from frame to frame)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageSequence

from . import colours
from .detect import MAX_FRAME, MIN_FRAME, TRANSPARENT, Analysis, Shape, load_keys
from .layout import SizeGroup, _fits

MAX_ENLARGED = 2048            # the biggest GIF checked for being an enlarged small picture
MAX_GIF_FRAMES = 2000          # a safety limit on what is read (sheets are split at 120 frames anyway)


@dataclass
class ScaleInfo:
    """What the detection found: a GIF whose pixels look like `factor` x `factor` blocks, with the block grid starting
    `phase` pixels from the left and top; or, for an enlargement by a fraction (such as 6.67x), `grid`: the real
    sprite size (cells across, cells down). `match` is the share of sprite pixels (0 to 1) that agree with the most
    common colour of their block (1.0 = an exact enlargement)."""
    factor: int = 1
    phase: tuple[int, int] = (0, 0)
    match: float = 1.0
    grid: tuple[int, int] | None = None

    @property
    def found(self) -> bool:
        return self.factor > 1 or self.grid is not None


def ratio_text(r: float) -> str:
    """6.6666 -> '6.67x', 2.5 -> '2.5x', 3.0 -> '3x'."""
    return f"{r:.2f}".rstrip("0").rstrip(".") + "x"


@dataclass
class GifOptions:
    background: int | None = None      # a colour key chosen by the user (None: detected)
    remove_repeats: bool = True        # drop a frame that is exactly the same as the one before it
    trim: bool = True                  # the box is the area that changes, not the whole GIF


@dataclass
class GifFrame:
    index: int                         # 0-based position in the GIF
    rgba: np.ndarray                   # (h, w, 4) uint8, the frame as the GIF shows it
    key: np.ndarray                    # (h, w) int32 colour keys, -1 = transparent
    repeat: bool = False               # same as the frame before it


@dataclass
class GifSheet:
    size: tuple[int, int]
    frames: list[GifFrame] = field(default_factory=list)
    had_alpha: bool = False
    partial_alpha: int = 0
    error: str = ""
    note: str = ""                       # shown to the user, for example that the GIF was reduced to its real size
    original_size: tuple[int, int] = (0, 0)               # the GIF as it is, before any reduction
    raw: list = field(default_factory=list)               # every frame as read (RGBA, colours cleaned up if chosen)
    raw_original: list = field(default_factory=list)      # every frame exactly as read
    lossy: bool = False                                   # a lossy WebP (its colours are smudged)
    cleanup: str | None = None                            # the clean-up strength in use, or None
    colours_before: int = 0                               # solid colours as read
    colours_after: int = 0                                # solid colours after clean-up
    scale: "ScaleInfo" = field(default_factory=lambda: ScaleInfo())
    factor: int = 1                                       # the pixel size used for `frames`
    grid_used: tuple[int, int] | None = None              # the real size used for a fractional enlargement
    too_big: bool = False                                 # the frames are over 128 pixels as they are now
    reduce_default: bool = False                          # what the Reduce switch starts as


@dataclass
class GifResult:
    analysis: Analysis | None = None
    groups: list[SizeGroup] = field(default_factory=list)
    kept: list[GifFrame] = field(default_factory=list)
    repeats_dropped: int = 0
    box: tuple[int, int, int, int] | None = None     # x0, y0, x1, y1 inside each frame
    background: int = TRANSPARENT
    message: str = ""


STRONG_MATCH = 0.98            # at least this share of sprite pixels agree with their block: reduce by default
WEAK_MATCH = 0.90              # at least this: suggest the reduction, switched off (below it: treated as 1:1)
EDGE_SHARE = 0.75              # the share of colour changes that must fall on the grid lines of a candidate size
MAX_FACTOR = 16                # the biggest enlargement looked for automatically (the user can pick up to 8)
SAMPLE_FRAMES = 12             # frames looked at when detecting (all frames are reduced)
MIN_EVIDENCE = 10              # distinct grid lines with colour changes needed, so a few plain squares never qualify
FRAC_SHARE = 0.5               # a fractional grid must hold at least half of the colour changes
FRAC_EXCESS = 0.25             # ... and this much more than an unrelated grid of the same number of lines would
FRAC_LINES = 8                 # distinct lines with colour changes needed each way before a fractional size is guessed


def _keys(rgba: np.ndarray) -> np.ndarray:
    """Colour keys of an RGBA frame: 0xRRGGBB, or TRANSPARENT where alpha is under 128 (as load_keys)."""
    a = rgba.astype(np.int32)
    key = (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]
    key[a[..., 3] < 128] = TRANSPARENT
    return key


def _rgba(key: np.ndarray) -> np.ndarray:
    out = np.zeros(key.shape + (4,), np.uint8)
    solid = key != TRANSPARENT
    out[..., 0] = (key >> 16) & 255
    out[..., 1] = (key >> 8) & 255
    out[..., 2] = key & 255
    out[..., 3] = np.where(solid, 255, 0)
    out[~solid, :3] = 0
    return out


def _sample(items: list) -> list:
    if len(items) <= SAMPLE_FRAMES:
        return items
    step = len(items) / SAMPLE_FRAMES
    return [items[int(i * step)] for i in range(SAMPLE_FRAMES)]


def _background(keys: list[np.ndarray]) -> int:
    if any((k == TRANSPARENT).any() for k in keys):
        return TRANSPARENT
    count: Counter = Counter()
    for k in keys:
        for edge in (k[0, :], k[-1, :], k[:, 0], k[:, -1]):
            count.update(edge.tolist())
    return count.most_common(1)[0][0]


def _changes(keys: list[np.ndarray], axis: int) -> np.ndarray:
    """How often the colour changes across each line between pixels (index i = the line before pixel i + 1)."""
    total = None
    for k in keys:
        d = (np.diff(k, axis=axis) != 0).sum(axis=1 - axis)
        total = d if total is None else total + d
    return total


def _phase(changes: np.ndarray, factor: int) -> tuple[int, float]:
    """The grid start (0 .. factor - 1) that the most colour changes fall on, and the share of changes that do."""
    n = int(changes.sum())
    if n == 0:
        return 0, 1.0
    pos = np.arange(1, len(changes) + 1) % factor
    sums = np.bincount(pos, weights=changes, minlength=factor)
    r = int(np.argmax(sums))
    return r, float(sums[r]) / n


def _blocks(key: np.ndarray, factor: int, x0: int, y0: int, nx: int, ny: int) -> np.ndarray:
    """The factor x factor blocks of `key` starting at (x0, y0): shape (ny, nx, factor * factor)."""
    part = key[y0:y0 + ny * factor, x0:x0 + nx * factor]
    return part.reshape(ny, factor, nx, factor).transpose(0, 2, 1, 3).reshape(ny, nx, factor * factor)


def _majority(blocks: np.ndarray) -> np.ndarray:
    """The most common colour of each block. Never a mixed colour: always one that is really in the block."""
    n = blocks.shape[-1]
    cand = np.sort(blocks, axis=-1)[..., n // 2]                    # holds the colour that fills more than half
    share = (blocks == cand[..., None]).sum(-1)
    out = cand.copy()
    for idx in zip(*np.nonzero(share * 2 <= n)):                    # no colour has more than half: count properly
        vals, counts = np.unique(blocks[idx], return_counts=True)
        out[idx] = vals[np.argmax(counts)]
    return out


def match_share(keys: list[np.ndarray], factor: int, phase: tuple[int, int], bg: int) -> float:
    """The share of pixels in sprite blocks (blocks holding any non-background pixel) that are the block's colour."""
    h, w = keys[0].shape
    ox, oy = phase
    nx, ny = (w - ox) // factor, (h - oy) // factor
    if nx < 1 or ny < 1:
        return 0.0
    agree = total = 0
    for k in keys:
        b = _blocks(k, factor, ox, oy, nx, ny)
        sprite = (b != bg).any(-1)
        if not sprite.any():
            continue
        m = _majority(b[sprite])
        agree += int((b[sprite] == m[:, None]).sum())
        total += int(sprite.sum()) * factor * factor
    return agree / total if total else 0.0


def detect_scale(frames: list[np.ndarray]) -> ScaleInfo:
    """Look for a whole-number enlargement in RGBA frames. The block grid may start part-way in (a border or an
    offset), and a few stray pixels are allowed. ScaleInfo() (factor 1) when nothing fits."""
    keys = [_keys(f) for f in _sample(frames)]
    h, w = keys[0].shape
    if w < 2 or h < 2:
        return ScaleInfo()
    bg = _background(keys)
    cx, cy = _changes(keys, 1), _changes(keys, 0)
    if int((cx > 0).sum() + (cy > 0).sum()) < MIN_EVIDENCE:
        return ScaleInfo()                                            # too little drawn to tell
    for factor in range(min(MAX_FACTOR, w // MIN_FRAME, h // MIN_FRAME), 1, -1):
        ox, sx = _phase(cx, factor)
        oy, sy = _phase(cy, factor)
        if min(sx, sy) < EDGE_SHARE:
            continue
        m = match_share(keys, factor, (ox, oy), bg)
        if m >= WEAK_MATCH:
            return ScaleInfo(factor, (ox, oy), m)
    grid = _fractional_grid(cx, cy, w, h)
    if grid is not None:
        m = grid_match(keys, grid, bg)
        if m >= WEAK_MATCH:
            return ScaleInfo(1, (0, 0), m, grid)
    return ScaleInfo()


def _grid_lines(length: int, cells: int) -> np.ndarray:
    """Where each cell after the first starts, when `cells` pixels were enlarged to `length` (nearest-neighbour). On an
    exact tie programs differ by one pixel, which _snap settles from the picture itself."""
    return np.ceil(np.arange(1, cells) * length / cells - 0.5).astype(np.int64)


def _window(length: int, cells: int) -> np.ndarray:
    """The pixel lines a grid's lines may fall on (index i = the line before pixel i + 1). Programs round an exact
    half-pixel tie differently, so a tie counts both ways; for cells of 3 pixels or more, the next line counts too."""
    x = np.arange(1, cells) * length / cells - 0.5
    lines = np.ceil(x - 1e-9).astype(np.int64)
    extra = [lines + 1] if length / cells >= 3 else [lines[np.abs(x - np.round(x)) < 1e-9] + 1]
    mask = np.zeros(max(0, length - 1), bool)
    for pos in [lines] + extra:
        pos = pos[(pos >= 1) & (pos <= length - 1)]
        mask[pos - 1] = True
    return mask


def _cell_count(changes: np.ndarray, length: int) -> tuple[int, float] | None:
    """The number of real pixels across one direction of a fractionally enlarged picture. Every grid of at least 1.5x
    is scored by the share of colour changes on its lines, and by how much that beats an unrelated grid with as many
    lines. Of the grids that clearly stand out, the coarsest that explains nearly as much as the best is chosen (a
    finer grid can hold a coarser one's lines too). None when no grid stands out."""
    total = float(changes.sum())
    if int((changes > 0).sum()) < FRAC_LINES:
        return None                                                   # too few edges: many grids would fit by chance
    found = []
    for cells in range(MIN_FRAME, int(length / 1.5) + 1):
        mask = _window(length, cells)
        share = float(changes[mask].sum()) / total
        excess = share - mask.sum() / max(1, length - 1)
        if share >= FRAC_SHARE and excess >= FRAC_EXCESS:
            found.append((cells, share))
    if not found:
        return None
    best = max(sh for _c, sh in found)
    return next((c, sh) for c, sh in found if sh >= best - 0.05)


def _fractional_grid(cx: np.ndarray, cy: np.ndarray, w: int, h: int) -> tuple[int, int] | None:
    """The real sprite size (cells across, cells down) of a picture enlarged by a fraction, or None."""
    gx, gy = _cell_count(cx, w), _cell_count(cy, h)
    if gx is None or gy is None:
        return None
    rx, ry = w / gx[0], h / gy[0]
    if abs(rx - ry) > 0.15 * max(rx, ry):                            # both ways must be enlarged by about as much
        return None
    return gx[0], gy[0]


def _snap(changes: np.ndarray, length: int, cells: int) -> np.ndarray:
    """Cell edges (0, starts of cells 2 .. n, length). Where programs may disagree by a pixel (an exact half-pixel tie,
    or any edge when cells are 3 pixels or more wide) the edge goes to the line where the colours actually change."""
    x = np.arange(1, cells) * length / cells - 0.5
    lines = np.ceil(x - 1e-9).astype(np.int64)
    tie = np.abs(x - np.round(x)) < 1e-9
    wide = length / cells >= 3
    out = [0]
    for p, t in zip(lines, tie):
        options = (p, p + 1, p - 1) if wide else ((p, p + 1) if t else (p,))
        cand = [c for c in options if 1 <= c <= length - 1 and c > out[-1]]
        if not cand:
            out.append(min(length - 1, out[-1] + 1))
            continue
        out.append(max(cand, key=lambda c: (changes[c - 1], c == p)))
    out.append(length)
    return np.array(out, np.int64)


def _samples(bounds: np.ndarray) -> np.ndarray:
    """Three pixels from the middle part of each cell (never its edges when the cell is wide enough)."""
    start, width = bounds[:-1], np.maximum(1, bounds[1:] - bounds[:-1])
    inner = np.where(width >= 3, 1, 0)
    span = np.maximum(1, width - 2 * inner)
    pick = [start + inner + np.minimum(span - 1, (span * f).astype(np.int64)) for f in (0.2, 0.5, 0.8)]
    return np.stack(pick, axis=1).reshape(-1)                         # cell by cell, three each


def _grid_bounds(keys: list[np.ndarray], grid: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    h, w = keys[0].shape
    return _snap(_changes(keys, 1), w, grid[0]), _snap(_changes(keys, 0), h, grid[1])


def _grid_blocks(key: np.ndarray, grid: tuple[int, int], bounds) -> np.ndarray:
    nx, ny = grid
    sx, sy = _samples(bounds[0]), _samples(bounds[1])
    return key[np.ix_(sy, sx)].reshape(ny, 3, nx, 3).transpose(0, 2, 1, 3).reshape(ny, nx, 9)


def grid_match(keys: list[np.ndarray], grid: tuple[int, int], bg: int) -> float:
    """Like match_share, for a fractional grid: the share of sampled sprite pixels that are their cell's colour."""
    bounds = _grid_bounds(keys, grid)
    agree = total = 0
    for k in keys:
        b = _grid_blocks(k, grid, bounds)
        sprite = (b != bg).any(-1)
        if not sprite.any():
            continue
        m = _majority(b[sprite])
        agree += int((b[sprite] == m[:, None]).sum())
        total += int(sprite.sum()) * 9
    return agree / total if total else 0.0


def reduce_to_grid(frames: list[np.ndarray], grid: tuple[int, int]) -> list[np.ndarray]:
    """Each cell of a fractional grid becomes one pixel: the most common colour of pixels taken from its middle."""
    keys = [_keys(f) for f in frames]
    bounds = _grid_bounds(_sample(keys), grid)
    return [_rgba(_majority(_grid_blocks(k, grid, bounds))) for k in keys]


def phase_for(frames: list[np.ndarray], factor: int) -> tuple[int, int]:
    """The best grid start for a pixel size the user chose."""
    keys = [_keys(f) for f in _sample(frames)]
    return _phase(_changes(keys, 1), factor)[0], _phase(_changes(keys, 0), factor)[0]


def reduce_frames(frames: list[np.ndarray], factor: int, phase: tuple[int, int]) -> list[np.ndarray]:
    """Each factor x factor block becomes one pixel of its most common colour. A part-block strip at an edge is
    dropped when it is background in every frame; otherwise it becomes a whole pixel, so no sprite pixel is lost."""
    keys = [_keys(f) for f in frames]
    h, w = keys[0].shape
    bg = _background(_sample(keys))
    ox, oy = phase

    def plain(sl) -> bool:
        return all((k[sl] == bg).all() for k in keys)

    left = ox if ox and not plain((slice(None), slice(0, ox))) else 0
    top = oy if oy and not plain((slice(0, oy), slice(None))) else 0
    rx, ry = (w - ox) % factor, (h - oy) % factor
    right = rx if rx and not plain((slice(None), slice(w - rx, w))) else 0
    bottom = ry if ry and not plain((slice(h - ry, h), slice(None))) else 0
    x0, x1 = (ox - left), (w - rx + right)                         # the region kept, before padding
    y0, y1 = (oy - top), (h - ry + bottom)
    pad = ((factor - top) % factor if top else 0, (factor - bottom) % factor if bottom else 0)
    padx = ((factor - left) % factor if left else 0, (factor - right) % factor if right else 0)
    out = []
    for k in keys:
        part = np.pad(k[y0:y1, x0:x1], (pad, padx), mode="edge")   # a part-block is filled from its own pixels
        ny, nx = part.shape[0] // factor, part.shape[1] // factor
        out.append(_rgba(_majority(_blocks(part, factor, 0, 0, nx, ny))))
    return out


def read_gif(img: Image.Image, reduce: bool | None = None, pixel_size: int | None = None, lossy: bool = False,
             cleanup: str | None = "auto") -> GifSheet:
    """Read every frame and look for a whole-number enlargement. `pixel_size` None means Auto: the detected size is
    used when `reduce` is on. `reduce` None means the default: on for a strong match, and always for a GIF over 128
    pixels (it could not be used otherwise); a weaker match is only suggested. A GIF outside 4 to 128 pixels after
    that is refused. A lossy WebP (`lossy`) has its colours cleaned up first: `cleanup` "auto" uses the default
    strength for a lossy file and none otherwise, None turns it off, or a strength name."""
    w, h = img.size
    sheet = GifSheet((w, h))
    sheet.original_size = (w, h)
    if min(w, h) < MIN_FRAME or max(w, h) > MAX_ENLARGED:
        sheet.error = f"Frames are {w} x {h}. Sprite sizes must be {MIN_FRAME} to {MAX_FRAME} pixels."
        return sheet
    raw = []
    for i, frame in enumerate(ImageSequence.Iterator(img)):
        if i >= MAX_GIF_FRAMES:
            break
        raw.append(np.asarray(frame.convert("RGBA")).copy())
    if not raw:
        sheet.error = "No frames were found in this picture."
        return sheet
    sheet.raw_original, sheet.lossy = raw, lossy
    sheet.colours_before = colours.colour_count(raw)
    if cleanup == "auto":
        cleanup = colours.DEFAULT_STRENGTH if lossy else None
    set_cleanup(sheet, cleanup, reduce, pixel_size)
    return sheet


def set_cleanup(sheet: GifSheet, cleanup: str | None, reduce: bool | None = None, pixel_size: int | None = None) -> None:
    """Clean up the colours (or not), look for an enlargement again on the result, and rebuild the frames.
    `reduce` None uses the default for what is found."""
    raw = sheet.raw_original
    if cleanup:
        res = colours.clean_up(raw, cleanup)
        sheet.raw, sheet.colours_after = res.frames, res.after
    else:
        sheet.raw, sheet.colours_after = raw, sheet.colours_before
    sheet.cleanup = cleanup
    w, h = sheet.original_size
    sheet.scale = detect_scale(sheet.raw)
    too_big = w > MAX_FRAME or h > MAX_FRAME
    found = sheet.scale.found
    sheet.reduce_default = found and (too_big or sheet.scale.match >= STRONG_MATCH)
    apply_scale(sheet, sheet.reduce_default if reduce is None else reduce, pixel_size)


def apply_scale(sheet: GifSheet, reduce: bool, pixel_size=None) -> None:
    """(Re)build the frames from the GIF as read, at the chosen pixel size: `pixel_size` None means Auto (the detected
    size when `reduce` is on), a whole number means that many screen pixels per pixel, and ("grid", across, down)
    means a fractional enlargement reduced to that real size. When the result is still too big (or too small) the
    frames are kept for showing, with `error` set."""
    w, h = sheet.original_size
    sc = sheet.scale
    if pixel_size is None:
        if reduce and sc.grid is not None:
            pixel_size = ("grid", *sc.grid)
        else:
            pixel_size = sc.factor if reduce else 1
    sheet.factor, sheet.grid_used, sheet.error, sheet.note, sheet.frames = 1, None, "", "", []
    sheet.had_alpha, sheet.partial_alpha, sheet.too_big = False, 0, False
    raw = sheet.raw
    what = "The picture"
    partial = alpha_clear = None
    if isinstance(pixel_size, tuple):                                 # a fractional enlargement
        grid = (int(pixel_size[1]), int(pixel_size[2]))
        if grid == sc.grid:
            match = sc.match
        else:
            keys = [_keys(f) for f in _sample(raw)]
            match = grid_match(keys, grid, _background(keys))
        frames = reduce_to_grid(raw, grid)
        sw, sh = grid
        sheet.size, sheet.grid_used = (sw, sh), grid
        pct = f"{match * 100:.1f}".rstrip("0").rstrip(".")
        sheet.note = (f"{what} is {w} x {h}, a {ratio_text(w / sw)} enlargement of {sw} x {sh} ({pct}% of sprite "
                      f"pixels match). It was reduced to {sw} x {sh}; each pixel takes the most common colour from the "
                      "middle of its block, so no new colours appear.")
        if match < WEAK_MATCH:
            sheet.note += " It may not really be enlarged that much, so some pixels may be wrong."
        partial = round(sum(int(((f[..., 3] > 0) & (f[..., 3] < 255)).sum()) for f in raw) * sw * sh / (w * h))
        alpha_clear = any((f[..., 3] < 128).any() for f in raw)
    elif pixel_size > 1:
        factor = int(pixel_size)
        if factor == sc.factor:
            phase, match = sc.phase, sc.match
        else:
            phase = phase_for(raw, factor)
            keys = [_keys(f) for f in _sample(raw)]
            match = match_share(keys, factor, phase, _background(keys))
        frames = reduce_frames(raw, factor, phase)
        sh, sw = frames[0].shape[:2]
        sheet.size, sheet.factor = (sw, sh), factor
        pct = f"{match * 100:.1f}".rstrip("0").rstrip(".")
        if match >= 0.99999:
            sheet.note = (f"{what} is {w} x {h}, an exact {factor}x enlargement of {sw} x {sh}. It was reduced to "
                          f"{sw} x {sh}; no pixels were lost.")
        else:
            sheet.note = (f"{what} is {w} x {h}, a {factor}x enlargement of {sw} x {sh} ({pct}% of sprite pixels "
                          f"match). It was reduced to {sw} x {sh}; each pixel takes the most common colour of its "
                          "block, so no new colours appear.")
            if match < WEAK_MATCH:
                sheet.note += (f" It may not really be a {factor}x enlargement, so some pixels may be wrong. "
                               "Auto may find its real size.")
        partial = sum(int(((f[..., 3] > 0) & (f[..., 3] < 255)).sum()) for f in raw) // (factor * factor)
        alpha_clear = any((f[..., 3] < 128).any() for f in raw)
    else:
        frames = raw
        sheet.size = (w, h)
        if sc.found:
            sw, sh = sc.grid if sc.grid else ((w - sc.phase[0]) // sc.factor, (h - sc.phase[1]) // sc.factor)
            how = ratio_text(w / sw) if sc.grid else f"{sc.factor}x"
            pct = f"{sc.match * 100:.1f}".rstrip("0").rstrip(".")
            sheet.note = (f"This picture looks like a {how} enlargement of about {sw} x {sh} ({pct}% of sprite "
                          f"pixels match). Tick Reduce to real pixel size to use it at {sw} x {sh}.")
    sw, sh = sheet.size
    for i, rgba in enumerate(frames):
        key, clear, part = load_keys(Image.fromarray(rgba, "RGBA"))
        sheet.had_alpha |= clear
        sheet.partial_alpha += part
        sheet.frames.append(GifFrame(i, rgba, key))
    if partial is not None:
        sheet.had_alpha, sheet.partial_alpha = sheet.had_alpha or alpha_clear, partial
    mark_repeats(sheet.frames)
    if not sheet.frames:
        sheet.error = "No frames were found in this picture."
    elif max(sw, sh) > MAX_FRAME or min(sw, sh) < MIN_FRAME:
        sheet.too_big = max(sw, sh) > MAX_FRAME
        if (sw, sh) == (w, h):
            sheet.error = f"Frames are {w} x {h}. Sprite sizes must be {MIN_FRAME} to {MAX_FRAME} pixels."
        else:
            sheet.error = (f"Frames are {w} x {h} (reduced to {sw} x {sh}). "
                           f"Sprite sizes must be {MIN_FRAME} to {MAX_FRAME} pixels.")


def mark_repeats(frames: list[GifFrame]) -> None:
    """A frame that is exactly the same as the frame before it is a repeat."""
    for a, b in zip(frames, frames[1:]):
        b.repeat = bool(np.array_equal(a.key, b.key))


def detect_background(sheet: GifSheet) -> int:
    """Transparent pixels if there are any; otherwise the commonest colour on the border of all the frames."""
    if sheet.had_alpha:
        return TRANSPARENT
    count: Counter = Counter()
    for f in sheet.frames:
        k = f.key
        for edge in (k[0, :], k[-1, :], k[:, 0], k[:, -1]):
            count.update(edge.tolist())
    return count.most_common(1)[0][0]


def build(sheet: GifSheet, opts: GifOptions, toggled: set[int] | None = None) -> GifResult:
    """Choose the frames to keep, find the box, and build the Analysis and size group the output code needs.
    `toggled` holds the frames the user clicked: their state is the opposite of what the program decided."""
    res = GifResult()
    if sheet.error or not sheet.frames:
        res.message = sheet.error
        return res
    toggled = toggled or set()
    bg = opts.background if opts.background is not None else detect_background(sheet)
    res.background = bg
    kept: list[GifFrame] = []
    for f in sheet.frames:
        dropped = f.repeat and opts.remove_repeats
        if f.index in toggled:
            dropped = not dropped
        if dropped:
            if f.repeat and opts.remove_repeats and f.index not in toggled:
                res.repeats_dropped += 1
        else:
            kept.append(f)
    res.kept = kept
    w, h = sheet.size
    if not kept:
        res.message = "No frames are kept."
        return res
    if opts.trim:
        union = np.zeros((h, w), bool)
        for f in kept:
            union |= f.key != bg
        ys, xs = np.nonzero(union)
        if len(ys) == 0:
            res.message = "No sprites were found. Check the background colour."
            return res
        box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    else:
        box = (0, 0, w - 1, h - 1)
    res.box = box
    x0, y0, x1, y1 = box
    key = np.concatenate([f.key for f in kept], axis=0)                 # the virtual sheet: frames stacked downwards
    a = Analysis((w, h * len(kept)), key, bg, had_alpha=sheet.had_alpha, partial_alpha=sheet.partial_alpha)
    shapes = []
    for n, f in enumerate(kept):
        top = n * h
        mask = f.key[y0:y1 + 1, x0:x1 + 1] != bg
        s = Shape(n + 1, (x0, top + y0, x1, top + y1), "grid", mask, int(mask.sum()), bg, row=n)
        shapes.append(s)
    a.shapes = shapes
    res.analysis = a
    group = SizeGroup(x1 - x0 + 1, y1 - y0 + 1, shapes, _fits(x1 - x0 + 1, y1 - y0 + 1))
    res.groups = [group]
    return res
