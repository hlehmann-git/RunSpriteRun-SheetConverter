"""The GIF window: open an animated GIF, see its frames, drop the ones you do not want, and save the frames as a
RunSpriteRun sheet (PRD section 10)."""
from __future__ import annotations

from html import escape
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..core.gif import GifOptions
from ..core.output import build_sheets
from ..core.detect import Options
from ..version import VERSION
from .adjust_panel import Swatch
from .frame_strip import FrameStrip
from .gif_session import GifSession
from .output_mixin import OutputMixin
from .output_panel import OutputPanel
from .theme import STYLE

TITLE = "RunSpriteRun Sheet Converter"
GIF_FILTER = "GIF animations (*.gif);;All files (*)"


def _panel() -> QFrame:
    f = QFrame()
    f.setObjectName("panel")
    return f


class GifWindow(OutputMixin, QMainWindow):
    start_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"GIF animation - {TITLE}")
        self.setMinimumSize(1024, 720)
        self.resize(1280, 800)
        self.setStyleSheet(STYLE)
        self.session: GifSession | None = None
        self._last_dir = ""

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(10)
        outer.addLayout(top, 5)

        left = _panel()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 8, 10, 8)
        self.title_label = QLabel("GIF animation")
        self.title_label.setObjectName("head")
        ll.addWidget(self.title_label)
        self.hint = QLabel("Open a GIF (File, Open GIF). Click a frame to keep or drop it.")
        self.hint.setObjectName("dim")
        ll.addWidget(self.hint)
        self.strip = FrameStrip()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.strip)
        self.scroll.setWidgetResizable(True)
        ll.addWidget(self.scroll, 1)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        ll.addWidget(self.summary)
        self.box_label = QLabel("")
        self.box_label.setObjectName("dim")
        self.box_label.setWordWrap(True)
        ll.addWidget(self.box_label)
        self.error_label = QLabel("")
        self.error_label.setObjectName("orange")
        self.error_label.setWordWrap(True)
        ll.addWidget(self.error_label)
        top.addWidget(left, 3)

        right = _panel()
        right.setMinimumWidth(470)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 8, 12, 8)
        rl.setSpacing(4)
        head = QHBoxLayout()
        t = QLabel("Adjust")
        t.setObjectName("head")
        d = QLabel("The frames redraw at once")
        d.setObjectName("dim")
        head.addWidget(t)
        head.addWidget(d)
        head.addStretch()
        rl.addLayout(head)
        rl.addWidget(self._section("Background"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Background colour"), 1)
        self.bg_swatch = Swatch()
        self.bg_text = QLabel("")
        self.bg_text.setObjectName("dim")
        self.bg_pick = QPushButton("Pick")
        self.bg_pick.setCheckable(True)
        self.bg_auto = QPushButton("Auto")
        row.addWidget(self.bg_swatch)
        row.addWidget(self.bg_text)
        row.addStretch()
        row.addWidget(self.bg_pick)
        row.addWidget(self.bg_auto)
        rl.addLayout(row)
        note = QLabel("Click Pick, then click a pixel in a frame. That colour becomes transparent.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        rl.addWidget(note)
        rl.addWidget(self._section("Frames"))
        self.repeats = QCheckBox("Remove repeated frames")
        self.repeats.setChecked(True)
        self.trim = QCheckBox("Trim to the area that moves")
        self.trim.setChecked(True)
        rl.addWidget(self.repeats)
        rl.addWidget(self.trim)
        rl.addWidget(self._section("Pixel size"))
        self.reduce = QCheckBox("Reduce to real pixel size")
        self.reduce.setToolTip("Shrink a GIF that was enlarged by a whole number (2x, 3x ...) back to its real pixels")
        rl.addWidget(self.reduce)
        row = QHBoxLayout()
        row.addWidget(QLabel("Pixel size"), 1)
        self.pixel_size = QComboBox()
        self.pixel_size.addItem("Auto", None)
        for n in range(1, 9):
            self.pixel_size.addItem(f"{n}x", n)
        self.pixel_size.setToolTip("Auto uses the detected size. Choose a size by hand if Auto is wrong.")
        row.addWidget(self.pixel_size)
        rl.addLayout(row)
        self.scale_label = QLabel("")
        self.scale_label.setObjectName("dim")
        self.scale_label.setWordWrap(True)
        rl.addWidget(self.scale_label)
        lim = QLabel("Frames must be 4 to 128 pixels each way after any reduction. Each new pixel takes the most "
                     "common colour of its block, so no new colours appear.")
        lim.setObjectName("dim")
        lim.setWordWrap(True)
        rl.addWidget(lim)
        rl.addStretch()
        top.addWidget(right, 2)

        self.output = OutputPanel()
        outer.addWidget(self.output, 4)
        self._out_timer = QTimer(self)
        self._out_timer.setSingleShot(True)
        self._out_timer.setInterval(150)
        self._out_timer.timeout.connect(self._rebuild_output)

        self._build_menu()
        self.strip.frame_clicked.connect(self._frame_clicked)
        self.strip.pixel_picked.connect(self._pixel_picked)
        self.repeats.toggled.connect(self._options_changed)
        self.trim.toggled.connect(self._options_changed)
        self.reduce.toggled.connect(self._scaling_changed)
        self.pixel_size.currentIndexChanged.connect(self._scaling_changed)
        self.bg_pick.toggled.connect(self._pick_toggled)
        self.bg_auto.clicked.connect(self._bg_auto)
        self.output.save_clicked.connect(self.save_now)
        self.output.browse_clicked.connect(self._browse)
        self.output.tick_changed.connect(self._ticks_changed)
        self._set_enabled(False)

    @staticmethod
    def _section(text: str) -> QLabel:
        lab = QLabel(text.upper())
        lab.setObjectName("section")
        return lab

    def _build_menu(self) -> None:
        bar = self.menuBar()
        bar.setNativeMenuBar(False)
        f = bar.addMenu("File")
        self.open_action = QAction("Open GIF...", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.triggered.connect(self.open_dialog)
        self.save_action = QAction("Save Sheets", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.save_now)
        start = QAction("Start Screen...", self)
        start.triggered.connect(self.start_requested)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        f.addAction(self.open_action)
        f.addAction(self.save_action)
        f.addSeparator()
        f.addAction(start)
        f.addAction(exit_action)
        h = bar.addMenu("Help")
        about = QAction("About", self)
        about.triggered.connect(self._about)
        h.addAction(about)

    def _about(self) -> None:
        QMessageBox.information(self, "About", f"{TITLE}\nVersion {VERSION}\n\nTurns the frames of an animated GIF "
                                "into a RunSpriteRun sprite sheet. It works offline and never changes your original "
                                "file.")

    # ---- opening ---------------------------------------------------------------------------------------------------
    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open GIF", self._last_dir, GIF_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> bool:
        try:
            with Image.open(path) as im:
                if im.format != "GIF":
                    raise ValueError("This is not a GIF file.")
                session = GifSession(im, path)
        except Exception as exc:
            QMessageBox.warning(self, TITLE, f"This file could not be opened as a GIF.\n\n{exc}")
            return False
        self._last_dir = str(Path(path).parent)
        self.session = session
        for w, set_value in ((self.reduce, lambda: self.reduce.setChecked(session.reduce)),
                             (self.pixel_size, lambda: self.pixel_size.setCurrentIndex(0))):
            w.blockSignals(True)
            set_value()
            w.blockSignals(False)
        self.session.set_options(GifOptions(None, self.repeats.isChecked(), self.trim.isChecked()))
        self.bg_pick.setChecked(False)
        self.strip.set_session(session)
        self.hint.setText("Click a frame to keep or drop it.")
        self.setWindowTitle(f"{Path(path).name} - {TITLE}")
        ow, oh = session.sheet.original_size
        self.title_label.setText(f"GIF animation: {Path(path).name}  ({ow} x {oh})")
        self._set_enabled(not session.error)
        self._refresh()
        if session.error:
            QMessageBox.warning(self, TITLE, f"This GIF cannot be converted as it is.\n\n{session.error}\n\n"
                                "If it is a smaller picture enlarged by a whole number, choose that Pixel size "
                                "(2x, 3x ...). A GIF enlarged by a fraction such as 2.5x cannot be reduced cleanly.")
        return True

    def _set_enabled(self, on: bool) -> None:
        for w in (self.bg_pick, self.bg_auto, self.repeats, self.trim):
            w.setEnabled(on)
        has = self.session is not None and bool(self.session.sheet.raw)
        self.pixel_size.setEnabled(has)
        self.reduce.setEnabled(has and self.session.detected_factor > 1 and self.pixel_size.currentData() is None)

    # ---- redraw ----------------------------------------------------------------------------------------------------
    def _refresh(self) -> None:
        s = self.session
        if not s:
            return
        self.error_label.setText(s.error or s.result.message or s.sheet.note)
        self.scale_label.setText(s.scale_text() if s.sheet.raw else "")
        self.summary.setText("" if s.error else s.summary())
        self.box_label.setText("" if s.error or s.result.message else s.box_text())
        if not s.error:
            b = s.result.background
            self.bg_swatch.set_key(b)
            self.bg_text.setText(s.background_text())
        self.strip.update()
        self._schedule_output()

    def _build_output(self):
        s = self.session
        if not s:
            return None
        r = s.result
        if s.error or r.analysis is None:
            from ..core.output import Result
            return Result(), [escape(s.error or r.message)] if (s.error or r.message) else []
        result = build_sheets(r.analysis, r.groups, s.stem, Options())
        refused = [escape(g.problem) for g in r.groups if g.problem]
        return result, refused

    def _has_content(self) -> bool:
        return bool(self.session and not self.session.error)

    # ---- the user ----------------------------------------------------------------------------------------------------
    def _options_changed(self, *_) -> None:
        if self.session:
            self.session.set_options(GifOptions(self.session.options.background, self.repeats.isChecked(),
                                                self.trim.isChecked()))
            self._refresh()

    def _scaling_changed(self, *_) -> None:
        if not self.session:
            return
        self.session.set_scaling(self.reduce.isChecked(), self.pixel_size.currentData())
        self._set_enabled(not self.session.error)
        self.strip.set_session(self.session)
        self._refresh()

    def _frame_clicked(self, index: int) -> None:
        if self.session:
            self.session.toggle_frame(index)
            self._refresh()

    def _pick_toggled(self, on: bool) -> None:
        self.strip.set_picking(on)
        self.hint.setText("Click a pixel in any frame to choose the background colour." if on else
                          "Click a frame to keep or drop it.")

    def _pixel_picked(self, index: int, x: int, y: int) -> None:
        if self.session and self.session.pick_background(index, x, y):
            self.bg_pick.setChecked(False)
            self._refresh()

    def _bg_auto(self) -> None:
        if self.session:
            self.bg_pick.setChecked(False)
            self.session.reset_background()
            self._refresh()

    def clear_selection(self) -> None:
        if self.bg_pick.isChecked():
            self.bg_pick.setChecked(False)

    def closeEvent(self, event) -> None:
        self._out_timer.stop()
        super().closeEvent(event)
