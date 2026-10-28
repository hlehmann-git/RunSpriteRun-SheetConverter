RunSpriteRun Sheet Converter (version 0.2.7)
============================================

A separate program from RunSpriteRun. It turns two kinds of source into RunSpriteRun boxed sprite sheets (PNG):
  - Convert from external sprite sheet: a PNG, BMP, GIF or WebP sheet drawn by someone else.
  - Convert from GIF or WebP animation: the frames of an animated GIF or WebP (up to 128 x 128 pixels after any reduction; a pixel-art GIF
    that was enlarged by a whole number, such as 3x or 4x, is found and can be reduced back to its real size).
Colours are always kept exactly as in the source; RunSpriteRun does its own colour check when you import the sheet.
The original file is never changed.

RUN FROM SOURCE (needs Python 3.12)
    pip install -r requirements.txt PySide6
    python main.py                      the start screen: choose GIF animation or external sprite sheet
    python main.py sheet.png            straight into the sprite sheet window
    python main.py animation.gif        straight into the animation window (an animated .webp too)

SPRITE SHEET WINDOW
    File > Open Sheet (Ctrl+O). Click a shape to remove or restore it (red cross). Ctrl+click, or drag a rectangle, to
    select sprites; "Group the selected sprites into one box" puts them on one sheet whose box is the widest and tallest
    of them. Esc, or a click on empty space, clears the selection. Pick, then click a pixel, to choose the background
    or cell colour (Auto goes back to automatic).
    A sheet saved by RunSpriteRun (or by this program) is recognised: each guide-line box is read as one sprite at
    the box size, empty boxes are skipped, and the text at the top and the colour bar underneath are left out. Picking
    a background or cell colour, or switching Cell colour Off, uses the normal search instead.

ANIMATION WINDOW (GIF or WebP)
    File > Open Animation (Ctrl+O). Zoom - and + (top right of the frames) change the size the frames are shown at;
    a new file, or a new Pixel size, starts at the size that fits. Click a frame to keep or drop it. Repeated frames are dropped for you (switch). The box
    is trimmed to the area that moves (switch). Pick, then click a pixel in a frame, to choose the background colour.
    Pixel size: every animation is checked for pixel art that was drawn bigger, by a whole number (2x, 3x ...) or by a
    fraction (such as 2.5x or 6.67x, where blocks are alternately 6 and 7 pixels wide). The block grid may start
    part-way in, and a few pixels may be off. When the animation has a transparent background, its outline is used
    first: a lossy WebP smudges the colours but keeps the outline pixel-sharp. Over 128 pixels it is reduced for you; under 128 it is reduced when the
    match is strong (98% or more) and only suggested when it is weaker (90 to 98%). "Reduce to real pixel size" turns
    it on or off; the Pixel size list (Auto, the detected real size such as "72 x 72 (6.67x)", and 1x to 8x) sets it by
    hand. Each new pixel takes the most common colour of its block (for a fraction, from the middle of the block), so
    no new colours appear. If the frames are still too big, they are shown anyway, the window says what to do, and
    the Pixel size section is outlined in orange.
    PNG and BMP sprite sheets are never scaled: they are always used 1:1.

WEBP FILES
    A lossless WebP keeps its colours exactly, like a PNG. A lossy WebP is compressed like a JPEG, so the edges of pixel
    art are smudged into many slightly different colours. For a lossy WebP the Colours section turns on "Clean up
    colours" for you: rare colours are merged into the main colour they are closest to (or, for a smudged edge, into
    the nearer of the two colours either side). Only colours already in the picture are used, and transparent pixels
    stay transparent. Strength has seven steps: Very low, Low and Medium-low keep more shades, Medium (the default)
    suits most files, Medium-high, High and Very high merge more for heavily compressed ones. The note shows the result, for example "Lossy WebP: 6099 colours, cleaned up to 11".
    For other files the switch is greyed out: their colours are already exact.

BOTH WINDOWS
    The bottom panel shows each sheet exactly as it will be saved, one tab per sheet. Untick "Save this sheet" for the
    ones you do not want, choose a folder, then Save Sheets (Ctrl+S). If a file exists you are asked: Replace or Cancel.
    Files are named <name>_RSR_<width>x<height>.png (more than 120 frames: <name>_RSR_part2_<width>x<height>.png).

COMMAND LINE (sprite sheets only)
    python convert_cli.py sheet.png --out Converted [--box same] [--tolerance 8] [--join-gap 3]
    python convert_cli.py sheet.webp [--clean auto|off|very-low|low|medium-low|medium|medium-high|high|very-high]     (auto: Medium for a lossy WebP)

TESTS
    pip install -r requirements-dev.txt PySide6
    python -m pytest
