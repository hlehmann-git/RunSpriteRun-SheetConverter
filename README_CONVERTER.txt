RunSpriteRun Sheet Converter (version 0.2.2)
============================================

A separate program from RunSpriteRun. It turns two kinds of source into RunSpriteRun boxed sprite sheets (PNG):
  - Convert from external sprite sheet: a PNG, BMP or GIF sheet drawn by someone else.
  - Convert from GIF animation: the frames of an animated GIF (up to 128 x 128 pixels after any reduction; a pixel-art GIF
    that was enlarged by a whole number, such as 3x or 4x, is found and can be reduced back to its real size).
Colours are always kept exactly as in the source; RunSpriteRun does its own colour check when you import the sheet.
The original file is never changed.

RUN FROM SOURCE (needs Python 3.12)
    pip install -r requirements.txt PySide6
    python main.py                      the start screen: choose GIF animation or external sprite sheet
    python main.py sheet.png            straight into the sprite sheet window
    python main.py animation.gif        straight into the GIF window

SPRITE SHEET WINDOW
    File > Open Sheet (Ctrl+O). Click a shape to remove or restore it (red cross). Ctrl+click, or drag a rectangle, to
    select sprites; "Group the selected sprites into one box" puts them on one sheet whose box is the widest and tallest
    of them. Esc, or a click on empty space, clears the selection. Pick, then click a pixel, to choose the background
    or cell colour (Auto goes back to automatic).

GIF WINDOW
    File > Open GIF (Ctrl+O). Click a frame to keep or drop it. Repeated frames are dropped for you (switch). The box
    is trimmed to the area that moves (switch). Pick, then click a pixel in a frame, to choose the background colour.
    Pixel size: every GIF is checked for a whole-number enlargement, even when the block grid starts part-way in or a
    few pixels are off. Over 128 pixels it is reduced for you; under 128 it is reduced when the match is strong (98% or
    more) and only suggested when it is weaker (90 to 98%). "Reduce to real pixel size" turns it on or off; the Pixel
    size list (Auto, 1x to 8x) sets it by hand. Each new pixel takes the most common colour of its block, so no new
    colours appear. A GIF enlarged by a fraction (such as 2.5x) cannot be reduced cleanly.
    PNG and BMP sprite sheets are never scaled: they are always used 1:1.

BOTH WINDOWS
    The bottom panel shows each sheet exactly as it will be saved, one tab per sheet. Untick "Save this sheet" for the
    ones you do not want, choose a folder, then Save Sheets (Ctrl+S). If a file exists you are asked: Replace or Cancel.
    Files are named <name>_RSR_<width>x<height>.png (more than 120 frames: <name>_RSR_part2_<width>x<height>.png).

COMMAND LINE (sprite sheets only)
    python convert_cli.py sheet.png --out Converted [--box same] [--tolerance 8] [--join-gap 3]

TESTS
    pip install -r requirements-dev.txt PySide6
    python -m pytest
