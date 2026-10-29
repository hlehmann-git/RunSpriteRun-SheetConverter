"""What the GIF window is working on, with no screen code: the opened GIF, the adjustments, the frames the user
clicked, and the result (kept frames, box, size group)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..core import colours, gif
from ..core.detect import rgb_of
from ..core.gif import GifOptions, GifResult, GifSheet


class GifSession:
    def __init__(self, image: Image.Image, path: str | Path = "", lossy: bool | None = None):
        self.path = Path(path) if path else None
        if lossy is None:
            lossy = colours.webp_kind(self.path) == "lossy" if self.path else False
        self.sheet: GifSheet = gif.read_gif(image, lossy=lossy)
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

    def set_cleanup(self, strength: str | None) -> None:
        """Turn colour clean-up on (a strength name) or off (None). The enlargement is looked for again."""
        count = len(self.sheet.frames)
        gif.set_cleanup(self.sheet, strength, None, self.pixel_size)
        self.reduce = self.sheet.reduce_default if self.pixel_size is None else self.reduce
        if len(self.sheet.frames) != count:
            self.toggled = set()
        self.recompute()

    def colours_text(self) -> str:
        sh = self.sheet
        return colours.clean_note(sh.lossy, sh.colours_before,
                                  sh.colours_after if sh.cleanup else None, sh.cleanup)

    @property
    def detected_factor(self) -> int:
        return self.sheet.scale.factor

    @property
    def found(self) -> bool:
        """An enlargement (whole or fractional) was detected."""
        return self.sheet.scale.found

    def grid_choice(self):
        """The Pixel size list entry for a detected fractional size: (text, data), or None."""
        sc, (w, h) = self.sheet.scale, self.sheet.original_size
        if sc.grid is None:
            return None
        return f"{sc.grid[0]} x {sc.grid[1]} ({gif.ratio_text(w / sc.grid[0])})", ("grid", *sc.grid)

    def scale_text(self) -> str:
        """One line for the Pixel size section."""
        sc, (w, h) = self.sheet.scale, self.sheet.original_size
        if not sc.found:
            return f"No enlargement found: the picture is used at {w} x {h}, one pixel per pixel."
        pct = f"{sc.match * 100:.1f}".rstrip("0").rstrip(".")
        if sc.grid:
            sw, sh = sc.grid
            how = gif.ratio_text(w / sw)
        else:
            sw, sh = (w - sc.phase[0]) // sc.factor, (h - sc.phase[1]) // sc.factor
            how = f"{sc.factor}x"
        return f"Detected: {how} enlargement of about {sw} x {sh} ({pct}% match)."

    def problem_text(self) -> str:
        """What is wrong and what to do, when the frames cannot be used as they are (else '')."""
        sh = self.sheet
        if not sh.error:
            return ""
        if not sh.too_big:
            return sh.error
        w, h = sh.size
        if self.found and not self.reduce and self.pixel_size is None:
            todo = "Tick Reduce to real pixel size below."
        elif self.found:
            todo = "Choose Auto in Pixel size below to use the detected size."
        else:
            todo = ("No enlargement was found. If it is pixel art drawn bigger, choose its size in Pixel size below; "
                    "otherwise make the picture smaller before converting it.")
        return f"Too big to use as it is: frames are {w} x {h}, and sprites can be 4 to 128 pixels. {todo}"

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
