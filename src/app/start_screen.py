"""The start screen: what would you like to convert?"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from ..version import VERSION
from .theme import STYLE

TITLE = "RunSpriteRun Sheet Converter"

CARD_STYLE = """
QPushButton#card { background: #2a2a30; border: 1px solid #3a3c46; border-radius: 12px; padding: 24px;
                   font-size: 20px; font-weight: 600; text-align: center; }
QPushButton#card:hover { border-color: #508cdc; background: #30323c; }
"""


class StartScreen(QMainWindow):
    gif_chosen = Signal()
    sheet_chosen = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.setMinimumSize(1024, 720)
        self.resize(1280, 800)
        self.setStyleSheet(STYLE + CARD_STYLE)
        bar = self.menuBar()
        bar.setNativeMenuBar(False)
        f = bar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        f.addAction(exit_action)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.addStretch(2)
        title = QLabel(TITLE)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 600;")
        sub = QLabel("What would you like to convert?")
        sub.setObjectName("dim")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(40)
        row = QHBoxLayout()
        row.addStretch()
        self.gif_button = self._card("Convert from GIF or WebP animation",
                                     "Turns the frames of an animated GIF or WebP into a RunSpriteRun sprite sheet.")
        self.sheet_button = self._card("Convert from external sprite sheet",
                                       "Finds the sprites on a sheet drawn by someone else and boxes them for "
                                       "RunSpriteRun.")
        row.addWidget(self.gif_button)
        row.addSpacing(40)
        row.addWidget(self.sheet_button)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch(3)
        foot = QLabel(f"Version {VERSION}  -  you can come back to this screen from the File menu")
        foot.setObjectName("dim")
        foot.setAlignment(Qt.AlignCenter)
        lay.addWidget(foot)
        self.gif_button.clicked.connect(self.gif_chosen)
        self.sheet_button.clicked.connect(self.sheet_chosen)

    def _card(self, title: str, text: str) -> QPushButton:
        b = QPushButton()
        b.setObjectName("card")
        b.setFixedSize(400, 200)
        lay = QVBoxLayout(b)
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setWordWrap(True)
        t.setStyleSheet("font-size: 20px; font-weight: 600; background: transparent;")
        t.setAttribute(Qt.WA_TransparentForMouseEvents)
        d = QLabel(text)
        d.setAlignment(Qt.AlignCenter)
        d.setWordWrap(True)
        d.setObjectName("dim")
        d.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addStretch()
        lay.addWidget(t)
        lay.addWidget(d)
        lay.addStretch()
        return b
