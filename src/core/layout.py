"""From the shapes found to size groups: numbering the frames in reading order, choosing the box size of each group
and placing each sprite in its box (PRD section 4: Order, Sprites of different sizes, Choosing box sizes, Placing a
sprite in a frame). Pure logic; shows nothing."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .detect import MAX_FRAME, MIN_FRAME, Analysis, Options, Shape

MAX_SHEET_FRAMES = 120


@dataclass
class SizeGroup:
    width: int
    height: int
    shapes: list[Shape] = field(default_factory=list)
    problem: str = ""                       # set when the box cannot be made (outside 4 to 128 pixels)

    @property
    def count(self) -> int:
        return len(self.shapes)

    @property
    def size_text(self) -> str:
        return f"{self.width} x {self.height}"


def assign_rows(shapes: list[Shape]) -> None:
    """Number the rows of sprites on the source sheet (sets Shape.row, from 0). A sprite joins a row when most of its
    height lies within the height the row's sprites already cover."""
    rows: list[dict] = []
    for s in sorted(shapes, key=lambda s: (s.box[1] + s.box[3], s.box[0])):
        y0, y1 = s.box[1], s.box[3]
        best, best_ov = None, 0.0
        for r in rows:
            top, bottom = float(np.median(r["tops"])), float(np.median(r["bottoms"]))
            ov = min(y1, bottom) - max(y0, top) + 1
            frac = ov / min(y1 - y0 + 1, bottom - top + 1)
            if frac > best_ov:
                best, best_ov = r, frac
        if best is not None and best_ov >= 0.5:
            best["members"].append(s)
            best["tops"].append(y0)
            best["bottoms"].append(y1)
        else:
            rows.append({"members": [s], "tops": [y0], "bottoms": [y1]})
    rows.sort(key=lambda r: float(np.median(r["tops"])))
    for n, r in enumerate(rows):
        for s in r["members"]:
            s.row = n


def reading_order(shapes: list[Shape]) -> list[Shape]:
    """Left to right, then top to bottom."""
    return sorted(shapes, key=lambda s: (s.row, s.box[0], s.box[1]))


def _fits(w: int, h: int) -> str:
    if MIN_FRAME <= w <= MAX_FRAME and MIN_FRAME <= h <= MAX_FRAME:
        return ""
    return f"Frames are {w} x {h}. Sprite sizes must be {MIN_FRAME} to {MAX_FRAME} pixels."


def make_groups(analysis: Analysis, opts: Options) -> list[SizeGroup]:
    """The size groups for the sprites that are kept. 'estimate': one group per row, merged when the sizes differ by
    no more than the size tolerance; 'same': one group for everything. The widest and tallest sprite sets the box."""
    shapes = analysis.kept()
    if not shapes:
        return []
    assign_rows(shapes)
    ordered = reading_order(shapes)
    if opts.box_mode == "same":
        w, h = max(s.width for s in ordered), max(s.height for s in ordered)
        return [SizeGroup(w, h, ordered, _fits(w, h))]
    by_row: dict[int, list[Shape]] = {}
    for s in ordered:
        by_row.setdefault(s.row, []).append(s)
    groups = [SizeGroup(max(s.width for s in m), max(s.height for s in m), m) for _, m in sorted(by_row.items())]
    return merge_groups(groups, opts.size_tolerance)


def merge_groups(groups: list[SizeGroup], tolerance: int) -> list[SizeGroup]:
    """Groups whose width and height each differ by no more than `tolerance` become one group at the larger size."""
    groups = [SizeGroup(g.width, g.height, list(g.shapes)) for g in groups]
    changed = True
    while changed:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]
                if abs(a.width - b.width) <= tolerance and abs(a.height - b.height) <= tolerance:
                    a.width, a.height = max(a.width, b.width), max(a.height, b.height)
                    a.shapes = a.shapes + b.shapes
                    del groups[j]
                    changed = True
                    break
            if changed:
                break
    for g in groups:
        g.shapes = sorted(g.shapes, key=lambda s: (s.row, s.box[0], s.box[1]))
        g.problem = _fits(g.width, g.height)
    return sorted(groups, key=lambda g: (g.shapes[0].row, g.shapes[0].box[0]))


def constrain(group: SizeGroup) -> None:
    """Constrain to sprite box: the widest and tallest sprite sets the box."""
    group.width = max(s.width for s in group.shapes)
    group.height = max(s.height for s in group.shapes)
    group.problem = _fits(group.width, group.height)


def sheet_parts(group: SizeGroup) -> list[list[Shape]]:
    """The group split into sheets of at most 120 frames."""
    return [group.shapes[i:i + MAX_SHEET_FRAMES] for i in range(0, len(group.shapes), MAX_SHEET_FRAMES)]
