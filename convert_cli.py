"""Convert a sprite sheet from the command line (stages 1 and 2 have no window yet).

    python convert_cli.py sheet.png --out Converted [--box same] [--tolerance 8] [--join-gap 3]
    python convert_cli.py sheet.webp --clean high      a lossy WebP is cleaned up at Medium unless told otherwise
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from src.core import colours, layout, output
from src.core.detect import Options, analyse
from src.io import save


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Convert a sprite sheet into RunSpriteRun boxed sprite sheets.")
    p.add_argument("sheet")
    p.add_argument("--out", default=str(save.default_folder()))
    p.add_argument("--box", default="estimate", choices=["estimate", "same"], help="how sprite boxes are sized")
    p.add_argument("--tolerance", type=int, default=8, help="size tolerance, 0 to 32 px")
    p.add_argument("--join-gap", type=int, default=3, help="join gap, 0 to 16 px")
    p.add_argument("--vertical", default="bottom", choices=["bottom", "centre"])
    p.add_argument("--keep-empty", action="store_true")
    p.add_argument("--keep-text", action="store_true", help="do not remove text and palettes")
    p.add_argument("--clean", default="auto", choices=["auto", "off", "low", "medium", "high"],
                   help="colour clean-up for a lossy WebP (auto: Medium for a lossy WebP, off otherwise)")
    args = p.parse_args(argv)
    opts = Options(join_gap=args.join_gap, size_tolerance=args.tolerance, box_mode=args.box, vertical=args.vertical,
                   keep_empty=args.keep_empty, remove_text=not args.keep_text)
    src = Path(args.sheet)
    try:
        img = Image.open(src)
        if getattr(img, "is_animated", False):
            print("Animated GIF and WebP files are converted in the window: python main.py " + src.name)
            return 1
        img.load()
    except Exception:
        print(f"{src.name} could not be read. It may not be a picture, or it may be damaged.")
        return 1
    if img.width > 4096 or img.height > 4096:
        print("The largest sheet accepted is 4,096 x 4,096 pixels.")
        return 1
    lossy = colours.webp_kind(src) == "lossy"
    strength = (colours.DEFAULT_STRENGTH if lossy else None) if args.clean == "auto" else \
        (None if args.clean == "off" else args.clean.capitalize())
    if lossy or strength:
        before = colours.colour_count([np.asarray(img.convert("RGBA"))])
        if strength:
            res = colours.clean_up([np.asarray(img.convert("RGBA"))], strength)
            img = Image.fromarray(res.frames[0], "RGBA")
        print(colours.clean_note("lossy" if lossy else "", before, res.after if strength else None, strength)
              if lossy else f"Colours cleaned up: {before} to {res.after} ({strength}).")
    a = analyse(img, opts)
    for m in a.messages:
        print(m)
    groups = layout.make_groups(a, opts)
    res = output.build_sheets(a, groups, src.stem, opts)
    removed = [s for s in a.shapes if s.removed]
    print(f"Found {len(a.kept())} sprites; {len(removed)} shapes removed (text, palettes, pictures, empty cells).")
    print("Sizes: " + ", ".join(f"{g.count} frames of {g.size_text}" for g in groups))
    for m in res.refused + res.messages:
        print(m)
    for s in res.sheets:
        for m in s.messages:
            print(f"{s.file_name}: {m}")
    written = save.save_sheets(res.sheets, Path(args.out), lambda files: True)
    for w in written:
        print("Saved", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
