"""What the converter window is working on, with no screen code: the opened sheet, the adjustments, the shapes the
user removed or restored by hand, the selected sprites, and the size groups. Pure logic, so it can be tested without
a window."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image

from ..core.detect import Analysis, Options, Shape, analyse, rgb_of
from ..core.layout import SizeGroup, constrain, make_groups, reading_order

Box = tuple[int, int, int, int]

GROUP_COLOURS = ((255, 160, 60), (80, 220, 255), (255, 235, 90), (130, 255, 120), (255, 120, 190),
                 (170, 150, 255), (255, 120, 100), (120, 255, 220), (210, 210, 210), (200, 255, 80))


def group_colour(index: int) -> tuple[int, int, int]:
    return GROUP_COLOURS[index % len(GROUP_COLOURS)]


class Session:
    """One opened sheet. `options` are the adjustments; `toggled` holds the boxes of shapes the user clicked (their
    state is the opposite of what the program decided). Sprites you grouped by hand stay grouped a recompute as long as the
    size group they belong to still exists."""

    def __init__(self, image: Image.Image, path: str | Path = "", options: Options | None = None):
        self.image = image.convert("RGBA")
        self.path = Path(path) if path else None
        self.options = options or Options()
        self.toggled: set[Box] = set()
        self.selected: set[Box] = set()
        self.moves: dict[Box, tuple[int, int]] = {}                         # sprite -> the size of the group it was put in by hand
        self.analysis: Analysis | None = None
        self.groups: list[SizeGroup] = []
        self.message = ""                                                   # the last refusal, for the window to show

    @property
    def stem(self) -> str:
        return self.path.stem if self.path else "sheet"

    # ---- recompute -------------------------------------------------------------------------------------------------
    def analyse(self, options: Options | None = None) -> Analysis:
        """The slow part: find the shapes. Safe to run on another thread; call `apply` with the result on the main one."""
        return analyse(self.image, replace(options or self.options))

    def apply(self, analysis: Analysis, options: Options | None = None) -> None:
        if options is not None:
            self.options = options
        self.analysis = analysis
        for s in analysis.shapes:
            if s.box in self.toggled:
                s.removed = not s.removed
                s.reason = "" if not s.removed else "removed by you"
        boxes = {s.box for s in analysis.kept()}
        self.selected &= boxes
        self.regroup()

    def regroup(self) -> None:
        a = self.analysis
        self.groups = make_groups(a, self.options) if a else []
        by_box = {s.box: s for s in a.shapes} if a else {}
        for box, size in list(self.moves.items()):
            shape = by_box.get(box)
            home = next((g for g in self.groups if shape in g.shapes), None)
            if shape is None or shape.removed or home is None:
                self.moves.pop(box, None)
                continue
            target = next((g for g in self.groups if (g.width, g.height) == size), None)
            if target is None:                              # a group made by hand: it is made again
                target = SizeGroup(size[0], size[1])
                self.groups.append(target)
            if home is not target:
                home.shapes.remove(shape)
                target.shapes.append(shape)
        self.groups = [g for g in self.groups if g.shapes]
        for g in self.groups:
            order = {id(s): n for n, s in enumerate(reading_order(a.kept()))}
            g.shapes.sort(key=lambda s: order[id(s)])
            constrain(g)                                    # a group that gained a bigger sprite grows to fit it
        self.groups.sort(key=lambda g: (g.shapes[0].row, g.shapes[0].box[0]))

    # ---- reading what is there -------------------------------------------------------------------------------------
    def kept_in_order(self) -> list[Shape]:
        return reading_order(self.analysis.kept()) if self.analysis else []

    def frame_numbers(self) -> dict[Box, int]:
        return {s.box: n + 1 for n, s in enumerate(self.kept_in_order())}

    def group_of(self, shape: Shape) -> int:
        for i, g in enumerate(self.groups):
            if shape in g.shapes:
                return i
        return -1

    def removed_count(self) -> int:
        return sum(1 for s in self.analysis.shapes if s.removed) if self.analysis else 0

    def summary(self) -> str:
        if not self.analysis:
            return ""
        if not self.groups:
            return "No sprites found."
        parts = [f"{g.count} frame{'s' if g.count != 1 else ''} of {g.width} x {g.height}" for g in self.groups]
        total = sum(g.count for g in self.groups)
        n = self.removed_count()
        tail = f"{total} frames" + (f", {n} shape{'s' if n != 1 else ''} removed (red cross)" if n else "")
        return ", ".join(parts) + "  -  " + tail

    def background_text(self) -> str:
        if not self.analysis:
            return ""
        b = self.analysis.background
        return "Transparent" if b < 0 else "#%02X%02X%02X" % rgb_of(b)

    def shape_at(self, x: int, y: int) -> Shape | None:
        """The smallest shape (kept or removed) whose rectangle holds the sheet pixel (x, y)."""
        if not self.analysis:
            return None
        best = None
        for s in self.analysis.shapes:
            x0, y0, x1, y1 = s.box
            if x0 <= x <= x1 and y0 <= y <= y1:
                if best is None or s.width * s.height < best.width * best.height:
                    best = s
        return best

    # ---- what the user does ----------------------------------------------------------------------------------------
    def toggle_shape(self, shape: Shape) -> None:
        """Click on a shape: remove it, or bring it back."""
        self.toggled ^= {shape.box}
        shape.removed = not shape.removed
        shape.reason = "removed by you" if shape.removed else ""
        self.selected.discard(shape.box)
        self.moves.pop(shape.box, None)
        self.regroup()

    def select(self, boxes, add: bool = False) -> None:
        kept = {s.box for s in self.analysis.kept()} if self.analysis else set()
        chosen = set(boxes) & kept
        self.selected = (self.selected | chosen) if add else chosen

    def toggle_selected(self, shape: Shape) -> None:
        if shape.removed:
            return
        self.selected ^= {shape.box}

    def selected_shapes(self) -> list[Shape]:
        return [s for s in self.analysis.kept() if s.box in self.selected] if self.analysis else []

    def selection_max_size(self) -> tuple[int, int] | None:
        """The width of the widest and the height of the tallest selected sprite."""
        sel = self.selected_shapes()
        return (max(x.width for x in sel), max(x.height for x in sel)) if sel else None

    def group_selected(self) -> str:
        """Put all the selected sprites, whatever groups they are in, into one new size group whose box is the
        widest and tallest of them."""
        size = self.selection_max_size()
        if size is None:
            self.message = "Select some sprites first."
            return self.message
        sel = self.selected_shapes()
        for s in sel:
            home = self.groups[self.group_of(s)]
            home.shapes.remove(s)
            self.moves[s.box] = size
        self.groups = [g for g in self.groups if g.shapes]
        target = next((g for g in self.groups if (g.width, g.height) == size), None)
        if target is None:
            target = SizeGroup(size[0], size[1])
            self.groups.append(target)
        target.shapes.extend(sel)
        order = {id(s): n for n, s in enumerate(self.kept_in_order())}
        target.shapes.sort(key=lambda s: order[id(s)])
        constrain(target)
        for g in self.groups:
            if g is not target:
                constrain(g)
        self.groups.sort(key=lambda g: (g.shapes[0].row, g.shapes[0].box[0]))
        self.message = ""
        return ""
