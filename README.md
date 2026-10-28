# RunSpriteRun Sheet Converter

A companion program to [RunSpriteRun](https://github.com/hlehmann-git/RunSpriteRun). It turns sprite sheets drawn
by someone else, and animated GIFs, into RunSpriteRun boxed sprite sheets (PNG) that RunSpriteRun can import.

- **External sprite sheets (PNG, BMP, GIF, WebP):** finds the sprites, lets you remove or group them, and writes one sheet
  per sprite size. Sheets are always used 1:1.
- **Animated GIFs and WebPs:** keeps or drops frames, trims to the area that moves, and finds a GIF that was enlarged by a
  whole number (2x, 3x ...) so it can be reduced back to its real pixels. No new colours are ever made.

Colours are kept exactly as in the source; RunSpriteRun checks them against your chosen system when you import.
A lossy WebP, whose colours are smudged by compression, can have them cleaned up back to a small palette, using
only colours already in the picture.
The original file is never changed. Full instructions are in `README_CONVERTER.txt`.

## Run from source

Needs Python 3.12 on Windows.

    pip install -r requirements.txt
    python main.py

## Tests

    pip install -r requirements-dev.txt
    python -m pytest

Some tests use real game sprite sheets that are not included here, because they belong to their games' owners.
Those tests are skipped automatically.

## Licence

MIT. See `LICENSE`.
