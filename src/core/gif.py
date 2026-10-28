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
    `phase` pixels from the left and top. `match` is the share of sprite pixels (0 to 1) that agree with the most
    common colour of their block (1.0 = an exact enlargement)."""
    factor: int = 1
    phase: tuple[int, int] = (0, 0)
    match: float = 1.0


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
    return ScaleInfo()


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
    found = sheet.scale.factor > 1
    sheet.reduce_default = found and (too_big or sheet.scale.match >= STRONG_MATCH)
    apply_scale(sheet, sheet.reduce_default if reduce is None else reduce, pixel_size)


def apply_scale(sheet: GifSheet, reduce: bool, pixel_size: int | None = None) -> None:
    """(Re)build the frames from the GIF as read, at the chosen pixel size."""
    w, h = sheet.original_size
    sc = sheet.scale
    factor = pixel_size if pixel_size else (sc.factor if reduce else 1)
    sheet.factor, sheet.error, sheet.note, sheet.frames = factor, "", "", []
    sheet.had_alpha, sheet.partial_alpha = False, 0
    raw = sheet.raw
    if factor > 1:
        if factor == sc.factor:
            phase, match = sc.phase, sc.match
        else:
            phase = phase_for(raw, factor)
            keys = [_keys(f) for f in _sample(raw)]
            match = match_share(keys, factor, phase, _background(keys))
        frames = reduce_frames(raw, factor, phase)
        sh, sw = frames[0].shape[:2]
        sheet.size = (sw, sh)
        pct = f"{match * 100:.1f}".rstrip("0").rstrip(".")
        if match >= 0.99999:
            sheet.note = (f"The GIF is {w} x {h}, an exact {factor}x enlargement of {sw} x {sh}. It was reduced to "
                          f"{sw} x {sh}; no pixels were lost.")
        else:
            sheet.note = (f"The GIF is {w} x {h}, a {factor}x enlargement of {sw} x {sh} ({pct}% of sprite pixels "
                          f"match). It was reduced to {sw} x {sh}; each pixel takes the most common colour of its "
                          "block, so no new colours appear.")
            if match < WEAK_MATCH:
                sheet.note += (f" It may not really be a {factor}x enlargement (for example 2.5x, which cannot be "
                               "reduced cleanly), so some pixels may be wrong.")
        if not (MIN_FRAME <= min(sw, sh) and max(sw, sh) <= MAX_FRAME):
            sheet.error = (f"Frames are {w} x {h} ({factor}x enlarged, {sw} x {sh} underneath). "
                           f"Sprite sizes must be {MIN_FRAME} to {MAX_FRAME} pixels.")
            return
        partial = sum(int(((f[..., 3] > 0) & (f[..., 3] < 255)).sum()) for f in raw) // (factor * factor)
        alpha_clear = any((f[..., 3] < 128).any() for f in raw)
    else:
        frames = raw
        sheet.size = (w, h)
        if sc.factor > 1:
            sw, sh = (w - sc.phase[0]) // sc.factor, (h - sc.phase[1]) // sc.factor
            pct = f"{sc.match * 100:.1f}".rstrip("0").rstrip(".")
            sheet.note = (f"This GIF looks like a {sc.factor}x enlargement of about {sw} x {sh} ({pct}% of sprite "
                          f"pixels match). Tick Reduce to real pixel size to use it at {sw} x {sh}.")
        if w > MAX_FRAME or h > MAX_FRAME:
            sheet.error = f"Frames are {w} x {h}. Sprite sizes must be {MIN_FRAME} to {MAX_FRAME} pixels."
            return
        partial, alpha_clear = None, None
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
