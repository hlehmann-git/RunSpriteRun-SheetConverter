"""Which window is showing: the start screen, the sheet window or the GIF window."""
from __future__ import annotations

from .gif_window import GifWindow
from .main_window import MainWindow
from .start_screen import StartScreen


class Launcher:
    def __init__(self):
        self.start = StartScreen()
        self.start.gif_chosen.connect(lambda: self.show_mode("gif"))
        self.start.sheet_chosen.connect(lambda: self.show_mode("sheet"))
        self.current = None

    def show_start(self) -> None:
        self._close_current()
        self.start.show()
        self.start.raise_()

    def show_mode(self, mode: str):
        self._close_current()
        win = GifWindow() if mode == "gif" else MainWindow()
        win.start_requested.connect(self.show_start)
        self.current = win
        self.start.hide()
        win.show()
        return win

    def _close_current(self) -> None:
        win, self.current = self.current, None
        if win is not None:
            try:
                win.start_requested.disconnect()
            except (RuntimeError, TypeError):
                pass
            win.close()
            win.deleteLater()
