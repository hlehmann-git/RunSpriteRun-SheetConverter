"""What the GIF window is working on, with no screen code: the opened GIF, the adjustments, the frames the user
clicked, and the result (kept frames, box, size group)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..core import gif
from ..core.detect import rgb_of
from ..core.gif import GifOptions, GifResult, GifSheet


class GifSession:
    def __init__(self, image: Image.Image, path: str | Path = ""):
        self.path = Path(path) if path else None
        self.sheet: GifSheet = gif.read_gif(image)
        self.reduce: bool = self.sheet.reduce_default         # the Reduce to real pixel size switch
        self.pixel_size: int | None = None                    # None = Auto (the detected size), else 1 to 8
        self.options = GifOptions()
        self.toggled: set[int] = set()
        self.result: GifResult = GifResult()
        self.recompute()

    @property
    def stem(self) -> str:
        return self.path.stem if self.path else "animation"

    @property
    def error(self) -> str:
        return self.sheet.error

    def recompute(self) -> None:
        self.result = gif.build(self.sheet, self.options, self.toggled)

    def set_options(self, options: GifOptions) -> None:
        self.options = options
        self.recompute()

    def set_scaling(self, reduce: bool, pixel_size: int | None) -> None:
        """Rebuild the frames at another pixel size. Frames clicked off stay off when the frame count is unchanged."""
        self.reduce, self.pixel_size = reduce, pixel_size
        count = len(self.sheet.frames)
        if self.sheet.raw:
            gif.apply_scale(self.sheet, reduce, pixel_size)
        if len(self.sheet.frames) != count:
            self.toggled = set()
        self.recompute()

    @property
    def detected_factor(self) -> int:
        return self.sheet.scale.factor

    def scale_text(self) -> str:
        """One line for the Pixel size section."""
        sc, w, h = self.sheet.scale, *self.sheet.original_size
        if sc.factor == 1:
            return f"No enlargement found: the GIF is used at {w} x {h}, one pixel per pixel."
        pct = f"{sc.match * 100:.1f}".rstrip("0").rstrip(".")
        sw, sh = (w - sc.phase[0]) // sc.factor, (h - sc.phase[1]) // sc.factor
        return f"Detected: {sc.factor}x enlargement of about {sw} x {sh} ({pct}% match)."

    def toggle_frame(self, index: int) -> None:
        """Click on a frame: drop it if it is kept, keep it if it is dropped."""
        self.toggled ^= {index}
        self.recompute()

    def is_kept(self, index: int) -> bool:
        return any(f.index == index for f in self.result.kept)

    def pick_background(self, index: int, x: int, y: int) -> bool:
        """Use the colour of pixel (x, y) in frame `index` as the background. False if the pixel is outside."""
        w, h = self.sheet.size
        if not (0 <= x < w and 0 <= y < h) or not (0 <= index < len(self.sheet.frames)):
            return False
        self.options = GifOptions(int(self.sheet.frames[index].key[y, x]), self.options.remove_repeats, self.options.trim)
        self.recompute()
        return True

    def reset_background(self) -> None:
        self.options = GifOptions(None, self.options.remove_repeats, self.options.trim)
        self.recompute()

    def background_text(self) -> str:
        b = self.result.background
        return "Transparent" if b < 0 else "#%02X%02X%02X" % rgb_of(b)

    def summary(self) -> str:
        if self.error:
            return self.error
        r = self.result
        if r.message:
            return r.message
        n = len(r.kept)
        text = f"{n} frame{'s' if n != 1 else ''} kept"
        if r.repeats_dropped:
            text += f", {r.repeats_dropped} repeated frame{'s' if r.repeats_dropped != 1 else ''} dropped"
        dropped_by_hand = len(self.sheet.frames) - n - r.repeats_dropped
        if dropped_by_hand > 0:
            text += f", {dropped_by_hand} dropped by you"
        return text

    def box_text(self) -> str:
        g = self.result.groups[0] if self.result.groups else None
        if not g:
            return ""
        w, h = self.sheet.size
        how = "the area that moves" if self.options.trim and (g.width, g.height) != (w, h) else "the whole picture"
        return f"Box size: {g.width} x {g.height} ({how}; the GIF is {w} x {h})"
