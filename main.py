"""Start the RunSpriteRun Sheet Converter.

    python main.py                  the start screen
    python main.py sheet.png        straight into the sprite sheet window with that file
    python main.py animation.gif    straight into the GIF window with that file
"""
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.app.launcher import Launcher


def main() -> int:
    app = QApplication(sys.argv)
    launcher = Launcher()
    if len(sys.argv) > 1:
        path = sys.argv[1]
        win = launcher.show_mode("gif" if Path(path).suffix.lower() == ".gif" else "sheet")
        win.open_path(path)
    else:
        launcher.show_start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
