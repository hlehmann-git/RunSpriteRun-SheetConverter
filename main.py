"""Start the RunSpriteRun Sheet Converter.

    python main.py                  the start screen
    python main.py sheet.png        straight into the sprite sheet window with that file
    python main.py animation.gif    straight into the animation window with that file (an animated WebP too)
"""
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.app.launcher import Launcher


def is_animation(path: str) -> bool:
    """A .gif, or an animated .webp, opens in the animation window; anything else in the sprite sheet window."""
    suffix = Path(path).suffix.lower()
    if suffix == ".gif":
        return True
    if suffix == ".webp":
        try:
            from PIL import Image
            with Image.open(path) as im:
                return bool(getattr(im, "is_animated", False))
        except Exception:
            return False
    return False


def main() -> int:
    app = QApplication(sys.argv)
    launcher = Launcher()
    if len(sys.argv) > 1:
        path = sys.argv[1]
        win = launcher.show_mode("gif" if is_animation(path) else "sheet")
        win.open_path(path)
    else:
        launcher.show_start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
