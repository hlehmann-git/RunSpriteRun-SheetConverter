"""Finding the sprites on a sheet drawn by someone else (PRD section 4). Pure logic; shows nothing.

A sheet is read into one number per pixel (its "key"; -1 is transparent). The background is the transparent pixels,
or else the commonest colour on the border. Three things are looked for, in this order:

  1. Lines: a colour drawn as long thin lines (a lattice). The spaces between the lines are cells (kind A).
  2. Solid rectangles: a rectangle of one colour with a sprite in it is a cell (kind D). A rectangle that holds
     other rectangles, or is bigger than a frame can be, is a panel; inside a panel its own colour is the background.
  3. Loose sprites (kind B): whatever is left. Pixels that touch form a shape; shapes whose outlines are closer than
     the Join gap are joined; text and palettes are recognised and removed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .ccl import components, dilate

MIN_FRAME = 4
MAX_FRAME = 128
TRANSPARENT = -1


@dataclass
class Options:
    join_gap: int = 3                  # 0 to 16
    min_shape: int = 4                 # shapes of fewer pixels than this are specks and are ignored
    max_shape: int = 128               # shapes wider or taller than this are pictures and are removed
    remove_text: bool = True
    size_tolerance: int = 8            # 0 to 32
    box_mode: str = "estimate"         # "estimate" or "same"
    vertical: str = "bottom"           # "bottom" or "centre"
    keep_empty: bool = False
    background: int | None = None     # a colour key chosen by the user (None: detected)
    cell_colour: int | None = None    # a cell colour chosen by the user (None: detected)
    cells_off: bool = False            # the user switched cell detection off


@dataclass
class Shape:
    id: int
    box: tuple[int, int, int, int]     # x0, y0, x1, y1 inclusive; for a cell, the cell rectangle
    kind: str                          # "sprite" (loose), "cell" (solid rectangle) or "grid" (lattice / grid cell)
    mask: np.ndarray                   # the sprite's own pixels, box-sized
    pixels: int
    bg: int                            # the colour key that counts as see-through for this shape
    removed: bool = False
    reason: str = ""                   # why it was removed: text, palette, picture, empty
    row: int = 0

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0] + 1

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1] + 1


@dataclass
class Analysis:
    size: tuple[int, int]
    key: np.ndarray
    background: int
    cell_colour: int | None = None
    sheet_kinds: set[str] = field(default_factory=set)
    shapes: list[Shape] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    had_alpha: bool = False
    partial_alpha: int = 0

    def kept(self) -> list[Shape]:
        return [s for s in self.shapes if not s.removed]


def key_of(rgb: tuple[int, int, int]) -> int:
    return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def rgb_of(key: int) -> tuple[int, int, int]:
    return ((key >> 16) & 255, (key >> 8) & 255, key & 255)


def load_keys(img: Image.Image) -> tuple[np.ndarray, bool, int]:
    """(key array, True if any pixel is transparent, how many pixels were partly transparent). A pixel with alpha
    under 128 is transparent; one of 128 or more is solid."""
    rgba = np.asarray(img.convert("RGBA")).astype(np.int32)
    key = (rgba[..., 0] << 16) | (rgba[..., 1] << 8) | rgba[..., 2]
    clear = rgba[..., 3] < 128
    partial = int(((rgba[..., 3] > 0) & (rgba[..., 3] < 255)).sum())
    key[clear] = TRANSPARENT
    return key, bool(clear.any()), partial


def detect_background(key: np.ndarray, had_alpha: bool) -> int:
    """Transparent pixels if there are any; otherwise the commonest colour on the border."""
    if had_alpha:
        return TRANSPARENT
    border = np.concatenate([key[0, :], key[-1, :], key[:, 0], key[:, -1]])
    return Counter(border.tolist()).most_common(1)[0][0]


# ---------------------------------------------------------------------------------------------- lines (kind A)

def _hv_runs(mask: np.ndarray, min_len: int):
    """Long runs of True: list of (y, x0, x1) for rows (x1 exclusive)."""
    h, w = mask.shape
    m = np.zeros((h, w + 2), np.int8)
    m[:, 1:-1] = mask
    d = np.diff(m, axis=1)
    ys, xs = np.nonzero(d == 1)
    _, xe = np.nonzero(d == -1)
    keep = (xe - xs) >= min_len
    return ys[keep], xs[keep], xe[keep]


def _thin(mask: np.ndarray, y: int, x0: int, x1: int, limit: int = 3) -> bool:
    """True if the run on row y is a thin line: where it sits, the colour is at most `limit` pixels thick."""
    h = mask.shape[0]
    for x in (x0 + (x1 - x0) // 4, (x0 + x1) // 2, x0 + 3 * (x1 - x0) // 4):
        t, yy = 1, y - 1
        while yy >= 0 and mask[yy, x] and t <= limit:
            t += 1
            yy -= 1
        yy = y + 1
        while yy < h and mask[yy, x] and t <= limit:
            t += 1
            yy += 1
        if t > limit:
            return False
    return True


def find_lines(key: np.ndarray, background: int, min_len: int = 24, top: int = 40, tol: int = 24) -> np.ndarray | None:
    """The pixels drawn as long thin lines (a colour, or one very like it, in a run of 24 pixels or more that is at
    most 3 pixels thick). A lattice needs at least 4 lines across and 4 down; None if there is none. The lines
    across and the lines down may be different colours."""
    vals, counts = np.unique(key, return_counts=True)
    order = np.argsort(-counts)[:top]
    r, g, b = (key >> 16) & 255, (key >> 8) & 255, key & 255
    valid = key >= 0
    lines_h = np.zeros(key.shape, bool)
    lines_v = np.zeros(key.shape, bool)
    n_h = n_v = 0
    seen: set[int] = set()
    for idx in order:
        k = int(vals[idx])
        if k < 0 or k == background or counts[idx] < 4 * min_len or k in seen:
            continue
        rk, gk, bk = (k >> 16) & 255, (k >> 8) & 255, k & 255
        m = (np.abs(r - rk) <= tol) & (np.abs(g - gk) <= tol) & (np.abs(b - bk) <= tol) & valid
        if background >= 0:
            bgr, bgg, bgb = (background >> 16) & 255, (background >> 8) & 255, background & 255
            m &= ~((np.abs(r - bgr) <= tol) & (np.abs(g - bgg) <= tol) & (np.abs(b - bgb) <= tol))
        hy, hx0, hx1 = _hv_runs(m, min_len)
        mt = np.ascontiguousarray(m.T)
        vx, vy0, vy1 = _hv_runs(mt, min_len)
        for y, a_, b_ in zip(hy.tolist(), hx0.tolist(), hx1.tolist()):
            if _thin(m, y, a_, b_):
                lines_h[y, a_:b_] = True
                n_h += 1
        for x, a_, b_ in zip(vx.tolist(), vy0.tolist(), vy1.tolist()):
            if _thin(mt, x, a_, b_):
                lines_v[a_:b_, x] = True
                n_v += 1
        seen.add(k)
    if n_h >= 4 and n_v >= 4:
        return lines_h | lines_v
    return None


def lattice_cells(key: np.ndarray, background: int, lines: np.ndarray, min_cell: int = 16) -> list[tuple[int, int, int, int]]:
    """The closed spaces between the lines (the lines and the thin halo beside them are not part of a cell)."""
    comp = components(~lines, eight=False)
    h, w = key.shape
    out = []
    for x0, y0, x1, y1 in comp.boxes.tolist():
        if x0 == 0 or y0 == 0 or x1 == w - 1 or y1 == h - 1:
            continue                                         # the outside, not a cell
        cw, ch = x1 - x0 + 1, y1 - y0 + 1
        if min_cell <= cw <= MAX_FRAME and min_cell <= ch <= MAX_FRAME:
            out.append((x0, y0, x1, y1))
    return out


def _clusters(values: list[int], tol: int = 2) -> list[int]:
    """The typical value of each group of values that lie within `tol` of each other."""
    out, group = [], []
    for v in sorted(values):
        if group and v - group[-1] > tol:
            out.append(int(np.median(group)))
            group = []
        group.append(v)
    if group:
        out.append(int(np.median(group)))
    return out


def regularise_cells(cells: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Lines drawn by hand or compressed are a pixel out here and there: make cells that share a column (or a row)
    share the same left and right (or top and bottom)."""
    xs0 = _clusters([c[0] for c in cells])
    xs1 = _clusters([c[2] for c in cells])
    ys0 = _clusters([c[1] for c in cells])
    ys1 = _clusters([c[3] for c in cells])
    near = lambda v, options: min(options, key=lambda o: abs(o - v))
    return [(near(c[0], xs0), near(c[1], ys0), near(c[2], xs1), near(c[3], ys1)) for c in cells]


def missing_cells(cells: list[tuple[int, int, int, int]], boxes: list[tuple[int, int, int, int]]):
    """Cells of the same lattice where the lines were hidden by a sprite: for each box that sits in a column and a
    row of the lattice but in no cell, the cell it belongs to."""
    cols = sorted({(c[0], c[2]) for c in cells})
    rows = sorted({(c[1], c[3]) for c in cells})
    have = set(cells)
    out = {}
    for b in boxes:
        cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
        col = next((c for c in cols if c[0] <= cx <= c[1]), None)
        row = next((r for r in rows if r[0] <= cy <= r[1]), None)
        if col and row:
            cell = (col[0], row[0], col[1], row[1])
            if cell not in have:
                out[cell] = b
    return out


# ------------------------------------------------------------------------------ solid rectangles (kind D, panels)

@dataclass
class Rect:
    box: tuple[int, int, int, int]
    colour: int
    children: int = 0

    @property
    def area(self) -> int:
        return (self.box[2] - self.box[0] + 1) * (self.box[3] - self.box[1] + 1)


def find_rects(key: np.ndarray, background: int, skip: set[int], top: int = 60) -> list[Rect]:
    """Rectangles of one colour (a sprite may sit in them): the colour's pixels fill at least a quarter of the box,
    the box's outer ring is mostly that colour, and nothing in the box is background."""
    vals, counts = np.unique(key, return_counts=True)
    order = np.argsort(-counts)[:top]
    nonbg = key != background
    rects: list[Rect] = []
    seen: set[tuple[int, int, int, int]] = set()
    for idx in order:
        k = int(vals[idx])
        is_bg = k == background
        if k in skip or counts[idx] < 48:
            continue
        m = key == k
        comp = components(m, eight=False)
        H, W = key.shape
        for (x0, y0, x1, y1), n in zip(comp.boxes.tolist(), comp.sizes.tolist()):
            bw, bh = x1 - x0 + 1, y1 - y0 + 1
            if bw < 8 or bh < 8 or n * 4 < bw * bh:
                continue
            if is_bg and (x0 == 0 or y0 == 0 or x1 == W - 1 or y1 == H - 1):
                continue                                  # the real background, outside everything
            ring = np.concatenate([m[y0, x0:x1 + 1], m[y1, x0:x1 + 1], m[y0 + 1:y1, x0], m[y0 + 1:y1, x1]])
            if ring.mean() < 0.8:
                continue
            if not is_bg and nonbg[y0:y1 + 1, x0:x1 + 1].mean() < 0.98:
                continue
            if (x0, y0, x1, y1) in seen:
                continue
            seen.add((x0, y0, x1, y1))
            rects.append(Rect((x0, y0, x1, y1), k))
    return rects


def _inside(inner, outer) -> bool:
    return (inner != outer and inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2]
            and inner[3] <= outer[3])


# ------------------------------------------------------------------------------------- text and palettes

def _is_text_cluster(boxes: list, colours: int) -> bool:
    return len(boxes) >= 3 and colours <= 3 and all((b[2] - b[0] + 1) <= 14 and (b[3] - b[1] + 1) <= 12 for b in boxes)


def _near(a, b, gap: int) -> bool:
    return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])


def find_text(comp_boxes: np.ndarray, comp_colours: list[int], big_boxes: list | None = None) -> set[int]:
    """Numbers of the components that are text: three or more small shapes (each 12 pixels high or less) that follow
    one another along a line, in one to three colours."""
    n = len(comp_boxes)
    small = [i for i in range(n) if (comp_boxes[i][2] - comp_boxes[i][0] + 1) <= 14
             and (comp_boxes[i][3] - comp_boxes[i][1] + 1) <= 12]
    parent = {i: i for i in small}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    order = sorted(small, key=lambda i: (comp_boxes[i][1], comp_boxes[i][0]))
    for a_pos, a in enumerate(order):
        ax0, ay0, ax1, ay1 = comp_boxes[a]
        for b in order[a_pos + 1:]:
            bx0, by0, bx1, by1 = comp_boxes[b]
            if by0 > ay1 + 5:
                break
            hgap = max(bx0 - ax1, ax0 - bx1) - 1
            vgap = max(by0 - ay1, ay0 - by1) - 1
            if hgap <= 8 and vgap <= 4:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra
    clusters: dict[int, list[int]] = {}
    for i in small:
        clusters.setdefault(find(i), []).append(i)
    text: set[int] = set()
    for members in clusters.values():
        cols = len({comp_colours[i] for i in members})
        if not _is_text_cluster([tuple(comp_boxes[i]) for i in members], cols):
            continue
        if big_boxes and any(_near(comp_boxes[i], bb, 2) for i in members for bb in big_boxes):
            continue                                          # pieces of a bigger sprite (sparks, a gun), not text
        text.update(members)
    return text


def is_palette(key: np.ndarray, box: tuple[int, int, int, int], mask: np.ndarray) -> bool:
    """A strip or block made only of solid colour rectangles (a colour chart): the shape fills its box, has three
    or more colours, and each colour is itself a plain rectangle."""
    x0, y0, x1, y1 = box
    if not mask.all():
        return False
    crop = key[y0:y1 + 1, x0:x1 + 1]
    vals = np.unique(crop)
    if len(vals) < 3:
        return False
    for v in vals.tolist():
        m = crop == v
        ys, xs = np.nonzero(m)
        if (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1) != m.sum():
            return False
    return True


def _remove_words(key: np.ndarray, shapes: list[Shape]) -> None:
    """Words that the letter test missed (letters that touch): small shapes in one or two colours that stand in a line
    with other such shapes are text."""
    cand = []
    for s in shapes:
        if s.height <= 12 and s.width >= 4:
            crop = key[s.box[1]:s.box[3] + 1, s.box[0]:s.box[2] + 1][s.mask]
            if len(np.unique(crop)) <= 2:
                cand.append(s)
    for s in cand:
        for o in cand:
            if o is not s and abs(o.box[3] - s.box[3]) <= 2 and (min(abs(o.box[0] - s.box[2]), abs(s.box[0] - o.box[2])) <= 24
                                                                  or (o.box[0] <= s.box[2] and s.box[0] <= o.box[2])):
                s.removed, s.reason = True, "text"
                break


def _holds_only_text(s: Shape) -> bool:
    comp = components(s.mask, eight=True)
    if comp.count < 3 or comp.count > 60:
        return False
    boxes = comp.boxes
    if any((b[2] - b[0] + 1) > 14 or (b[3] - b[1] + 1) > 12 for b in boxes.tolist()):
        return False
    return True


# ---------------------------------------------------------------------------------------------- the analysis

def analyse(img: Image.Image, opts: Options | None = None) -> Analysis:
    opts = opts or Options()
    key, had_alpha, partial = load_keys(img)
    h, w = key.shape
    bg = opts.background if opts.background is not None else detect_background(key, had_alpha)
    a = Analysis((w, h), key, bg, had_alpha=had_alpha, partial_alpha=partial)
    shapes: list[Shape] = []

    def add(box, kind, mask, local_bg) -> Shape:
        s = Shape(len(shapes) + 1, box, kind, mask, int(mask.sum()), local_bg)
        shapes.append(s)
        return s

    lattice: list = []
    walls = np.zeros((h, w), bool)
    excluded = np.zeros((h, w), bool)
    local_bg = np.full((h, w), bg, np.int32)
    skip: set[int] = set()

    # 1. lines
    if not opts.cells_off:
        lines = find_lines(key, bg)
        if lines is not None:
            cells = lattice_cells(key, bg, lines)
            if len(cells) >= 4:
                skip |= set(np.unique(key[lines]).tolist())
                a.sheet_kinds.add("A")
                walls = dilate(lines, 1)
                excluded |= walls
                cells = list(dict.fromkeys(regularise_cells(cells)))
                lattice = cells[:]
                for (x0, y0, x1, y1) in cells:
                    excluded[y0:y1 + 1, x0:x1 + 1] = True
                    mask = (key[y0:y1 + 1, x0:x1 + 1] != bg) & ~walls[y0:y1 + 1, x0:x1 + 1]
                    add((x0, y0, x1, y1), "grid", mask, bg)

    # 2. solid rectangles
    if not opts.cells_off:
        rects = find_rects(key, bg, skip)
        if opts.cell_colour is not None:
            rects = [r for r in rects if r.colour == opts.cell_colour or r.area > MAX_FRAME * MAX_FRAME
                     or max(r.box[2] - r.box[0], r.box[3] - r.box[1]) + 1 > MAX_FRAME]
        rects = [r for r in rects if not excluded[r.box[1]:r.box[3] + 1, r.box[0]:r.box[2] + 1].any()]
        for r in rects:
            r.children = sum(1 for o in rects if _inside(o.box, r.box))
        cell_colours: Counter = Counter()
        for r in sorted(rects, key=lambda r: -r.area):
            x0, y0, x1, y1 = r.box
            big = (x1 - x0 + 1) > MAX_FRAME or (y1 - y0 + 1) > MAX_FRAME
            if r.children == 0 and not big:
                if excluded[y0:y1 + 1, x0:x1 + 1].any():
                    continue
                excluded[y0:y1 + 1, x0:x1 + 1] = True
                mask = key[y0:y1 + 1, x0:x1 + 1] != r.colour
                add(r.box, "cell", mask, r.colour)
                cell_colours[r.colour] += 1
                a.sheet_kinds.add("D")
            else:                                             # a panel: inside it, its own colour is the background
                local_bg[y0:y1 + 1, x0:x1 + 1] = r.colour
        if cell_colours:
            a.cell_colour = cell_colours.most_common(1)[0][0]

    # 3. loose sprites
    loose = (key != local_bg) & ~excluded
    if a.cell_colour is not None:
        loose &= key != a.cell_colour                       # a cell the rectangle test missed is still not sprite
    comp = components(loose, eight=True, want_labels=True)
    if comp.count:
        # the colour of each component: the commonest colour in it (cheap: its top-left run is enough for text tests)
        comp_cols = []
        for i, b in enumerate(comp.boxes.tolist()):
            sub = comp.labels[b[1]:b[3] + 1, b[0]:b[2] + 1] == i + 1
            vals = np.unique(key[b[1]:b[3] + 1, b[0]:b[2] + 1][sub])
            comp_cols.append(vals)
        text_ids: set[int] = set()
        if opts.remove_text:
            # treat each component as having as many colours as it holds, so a multi-colour blob is never text
            count_cols = [len(v) for v in comp_cols]
            ids = [i for i in range(comp.count) if count_cols[i] <= 3]
            sub_boxes = comp.boxes[ids] if ids else np.zeros((0, 4), np.int32)
            big = [tuple(b) for b in comp.boxes.tolist() if (b[3] - b[1] + 1) > 14]
            hit = find_text(sub_boxes, [int(comp_cols[i][0]) for i in ids], big) if ids else set()
            text_ids = {ids[j] for j in hit}
        text_mask = np.zeros((h, w), bool)
        for i in text_ids:
            b = comp.boxes[i]
            sub = comp.labels[b[1]:b[3] + 1, b[0]:b[2] + 1] == i + 1
            text_mask[b[1]:b[3] + 1, b[0]:b[2] + 1] |= sub
        removed_text_boxes = [tuple(comp.boxes[i]) for i in sorted(text_ids)]
        loose &= ~text_mask
        # palettes: whole solid-block shapes
        palette_mask = np.zeros((h, w), bool)
        palette_boxes = []
        for i, b in enumerate(comp.boxes.tolist()):
            if i in text_ids or len(comp_cols[i]) < 3:
                continue
            x0, y0, x1, y1 = b
            sub = comp.labels[y0:y1 + 1, x0:x1 + 1] == i + 1
            if opts.remove_text and is_palette(key, (x0, y0, x1, y1), sub):
                palette_mask[y0:y1 + 1, x0:x1 + 1] |= sub
                palette_boxes.append(tuple(b))
        loose &= ~palette_mask
        # join pieces that are close, then take each joined group as one sprite
        joined = components(dilate(loose, opts.join_gap // 2) & (loose | dilate(loose, opts.join_gap // 2)),
                            eight=True, want_labels=True)
        for i in range(joined.count):
            x0, y0, x1, y1 = joined.boxes[i].tolist()
            sub = (joined.labels[y0:y1 + 1, x0:x1 + 1] == i + 1) & loose[y0:y1 + 1, x0:x1 + 1]
            n = int(sub.sum())
            if n < opts.min_shape:
                continue
            ys, xs = np.nonzero(sub)
            box = (x0 + int(xs.min()), y0 + int(ys.min()), x0 + int(xs.max()), y0 + int(ys.max()))
            mask = sub[box[1] - y0:box[3] - y0 + 1, box[0] - x0:box[2] - x0 + 1]
            lbg = int(local_bg[box[1], box[0]])
            s = add(box, "sprite", mask, lbg)
            if s.width > opts.max_shape or s.height > opts.max_shape:
                s.removed, s.reason = True, "picture"
            a.sheet_kinds.add("B")
        if opts.remove_text:
            _remove_words(key, [s for s in shapes if s.kind == "sprite" and not s.removed])
        for b in removed_text_boxes:
            s = add(tuple(b), "sprite", np.ones((b[3] - b[1] + 1, b[2] - b[0] + 1), bool), bg)
            s.removed, s.reason = True, "text"
        for b in palette_boxes:
            s = add(tuple(b), "sprite", np.ones((b[3] - b[1] + 1, b[2] - b[0] + 1), bool), bg)
            s.removed, s.reason = True, "palette"

    # lattice cells whose lines were hidden: the loose shapes in them become the cell
    if lattice:
        for s in [s for s in shapes if s.kind == "sprite" and min(s.width, s.height) <= 2]:
            shapes.remove(s)                                    # left-over bits of the lines themselves
        loose_shapes = [s for s in shapes if s.kind == "sprite" and not s.removed]
        fixes = missing_cells(lattice, [s.box for s in loose_shapes])
        for cell, _ in fixes.items():
            inside = [s for s in loose_shapes if cell[0] <= (s.box[0] + s.box[2]) // 2 <= cell[2]
                      and cell[1] <= (s.box[1] + s.box[3]) // 2 <= cell[3]]
            for s in inside:
                shapes.remove(s)
            x0, y0, x1, y1 = cell
            mask = (key[y0:y1 + 1, x0:x1 + 1] != bg) & ~walls[y0:y1 + 1, x0:x1 + 1]
            shapes.append(Shape(0, cell, "grid", mask, int(mask.sum()), bg))
        for i, s in enumerate(shapes, 1):
            s.id = i
    # cells (and table boxes) that hold only text
    if opts.remove_text:
        for s in shapes:
            if s.kind in ("cell", "grid") and not s.removed and s.pixels and _holds_only_text(s):
                s.removed, s.reason = True, "text"
    # empty cells
    for s in shapes:
        if s.kind in ("cell", "grid") and s.pixels == 0:
            s.removed, s.reason = (not opts.keep_empty), "empty"
    # cells that hold nothing but text are left to the user
    a.shapes = shapes
    if not any(not s.removed for s in shapes):
        a.messages.append("No sprites were found. Check the background colour.")
    return a
