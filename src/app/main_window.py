"""The converter's main window, part 1: open a sheet, see the sprites outlined by size group, adjust, click shapes
to remove or restore them, select sprites and set their box size. The output preview and saving come in part 2."""
from __future__ import annotations

from html import escape
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QEvent, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QApplication,
                               QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QTabBar, QVBoxLayout, QWidget)

from ..core.detect import Options
from ..core.output import build_sheets
from ..version import VERSION
from .output_mixin import OutputMixin
from .output_panel import OutputPanel
from .adjust_panel import AdjustPanel, needs_analysis
from .session import Session
from .source_view import SourceView
from .theme import STYLE

TITLE = "RunSpriteRun Sheet Converter"
IMAGE_FILTER = "Sprite sheets (*.png *.bmp *.gif *.webp);;All files (*)"
DEBOUNCE_MS = 200


class _Done(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)


class _Job(QRunnable):
    """The slow search for sprites, on its own thread so the window stays alive."""

    def __init__(self, serial: int, session: Session, options: Options, done: _Done):
        super().__init__()
        self.serial, self.session, self.options, self.done = serial, session, options, done

    def run(self) -> None:
        try:
            result = self.session.analyse(self.options)
        except Exception as exc:                       # shown to the person, not lost
            self.done.failed.emit(self.serial, str(exc))
            return
        self.done.finished.emit(self.serial, result)


def _panel() -> QFrame:
    f = QFrame()
    f.setObjectName("panel")
    return f


class MainWindow(OutputMixin, QMainWindow):
    start_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.setMinimumSize(1024, 720)
        self.resize(1280, 800)
        self.setStyleSheet(STYLE)
        self.session: Session | None = None
        self._serial = 0
        self._pending: Options | None = None
        self._pick_which = ""
        self._last_dir = ""
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(1)
        self._done = _Done()
        self._done.finished.connect(self._analysed)
        self._done.failed.connect(self._analysis_failed)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._start_job)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(10)
        outer.addLayout(top, 5)

        # source panel
        src = _panel()
        sl = QVBoxLayout(src)
        sl.setContentsMargins(10, 8, 10, 8)
        head = QHBoxLayout()
        t = QLabel("Source sheet")
        t.setObjectName("head")
        self.title_label = t
        self.hint = QLabel("Click a shape to remove or restore it. Ctrl+click or drag to select sprites.")
        self.hint.setObjectName("dim")
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(QLabel("Zoom"))
        self.zoom_out = QPushButton("-")
        self.zoom_in = QPushButton("+")
        for b in (self.zoom_out, self.zoom_in):
            b.setFixedWidth(28)
        self.zoom_label = QLabel("1x")
        self.zoom_label.setMinimumWidth(24)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        head.addWidget(self.zoom_out)
        head.addWidget(self.zoom_label)
        head.addWidget(self.zoom_in)
        sl.addLayout(head)
        sl.addWidget(self.hint)
        self.view = SourceView()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.view)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        sl.addWidget(self.scroll, 1)
        self.summary = QLabel("Open a sprite sheet to begin (File, Open Sheet).")
        self.summary.setWordWrap(True)
        sl.addWidget(self.summary)
        self.status = QLabel("")
        self.status.setObjectName("orange")
        self.status.setWordWrap(True)
        sl.addWidget(self.status)
        top.addWidget(src, 3)

        self.panel = AdjustPanel()
        self.panel.setMinimumWidth(470)
        top.addWidget(self.panel, 2)

        self.output = OutputPanel()
        outer.addWidget(self.output, 4)
        self._out_timer = QTimer(self)
        self._out_timer.setSingleShot(True)
        self._out_timer.setInterval(150)
        self._out_timer.timeout.connect(self._rebuild_output)

        self._build_menu()
        self._escape = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._escape.setContext(Qt.WindowShortcut)
        self._escape.activated.connect(self.clear_selection)
        QApplication.instance().installEventFilter(self)

        self.zoom_out.clicked.connect(lambda: self._zoom(-1))
        self.zoom_in.clicked.connect(lambda: self._zoom(+1))
        self.view.shape_clicked.connect(self._shape_clicked)
        self.view.rect_selected.connect(self._rect_selected)
        self.view.pixel_picked.connect(self._pixel_picked)
        self.panel.options_changed.connect(self._options_changed)
        self.panel.pick_requested.connect(self._pick_requested)
        self.panel.group_requested.connect(self._group)
        self.panel.cleanup.changed.connect(self._cleanup_changed)
        self.output.save_clicked.connect(self.save_now)
        self.output.browse_clicked.connect(self._browse)
        self.output.tick_changed.connect(self._ticks_changed)
        self.output.frames_clicked.connect(self._select_frames)

    def closeEvent(self, event) -> None:
        QApplication.instance().removeEventFilter(self)
        self._serial += 1                               # a search still running is no longer wanted
        self._timer.stop()
        self._pool.waitForDone(30000)                   # let it finish before the window goes
        super().closeEvent(event)

    # ---- menu ------------------------------------------------------------------------------------------------------
    def _build_menu(self) -> None:
        bar = self.menuBar()
        bar.setNativeMenuBar(False)
        f = bar.addMenu("File")
        self.open_action = QAction("Open Sheet...", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.triggered.connect(self.open_dialog)
        self.save_action = QAction("Save Sheets", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.save_now)
        start_action = QAction("Start Screen...", self)
        start_action.triggered.connect(self.start_requested)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        for a in (self.open_action, self.save_action):
            f.addAction(a)
        f.addSeparator()
        f.addAction(start_action)
        f.addAction(exit_action)
        h = bar.addMenu("Help")
        about = QAction("About", self)
        about.triggered.connect(self._about)
        h.addAction(about)

    def _about(self) -> None:
        QMessageBox.information(self, "About", f"{TITLE}\nVersion {VERSION}\n\nTurns sprite sheets made by other "
                                "people into RunSpriteRun sheets. It works offline and never changes your original "
                                "file.")

    # ---- opening ---------------------------------------------------------------------------------------------------
    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Sheet", self._last_dir, IMAGE_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> bool:
        try:
            with Image.open(path) as im:
                im.load()
                img = im.copy()
        except Exception as exc:
            QMessageBox.warning(self, TITLE, f"This file could not be opened as a picture.\n\n{exc}")
            return False
        self._last_dir = str(Path(path).parent)
        self._serial += 1
        self._timer.stop()
        self.panel.reset_colours()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.session = Session(img, path, self.panel.options())
        finally:
            QApplication.restoreOverrideCursor()
        self.session.options = self.panel.options()
        self.panel.cleanup.set_file(self.session.lossy, self.session.cleanup, self.session.colours_text())
        self.panel.set_enabled_for_sheet(True)
        self.view.set_session(self.session, self._auto_zoom(img.width))
        self.zoom_label.setText(f"{self.view.zoom}x")
        self.setWindowTitle(f"{Path(path).name} - {TITLE}")
        self.title_label.setText(f"Source sheet: {Path(path).name}  ({img.width} x {img.height})")
        self.status.setText("")
        self._start_job()
        return True

    def _cleanup_changed(self, strength) -> None:
        """Clean up colours switched or its strength changed: the sheet is cleaned again and searched again."""
        if not self.session:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.session.set_cleanup(strength)
        finally:
            QApplication.restoreOverrideCursor()
        self.panel.cleanup.set_note(self.session.colours_text())
        self.view.set_session(self.session, self.view.zoom)          # show the cleaned (or original) colours
        self._start_job()

    def _auto_zoom(self, width: int) -> int:
        room = max(200, self.scroll.viewport().width() - 4)
        return max(1, min(4, room // max(1, width)))

    # ---- searching -------------------------------------------------------------------------------------------------
    def _options_changed(self) -> None:
        if not self.session:
            return
        new = self.panel.options()
        if needs_analysis(self.session.options, new) or self.session.analysis is None:
            self._pending = new
            self.summary.setText("Working...")
            self._timer.start()
        else:
            self.session.options = new
            self.session.regroup()
            self._refresh()

    def _start_job(self) -> None:
        if not self.session:
            return
        opts = self._pending or self.panel.options()
        self._pending = None
        self._serial += 1
        self.summary.setText("Working...")
        self._pool.start(_Job(self._serial, self.session, opts, self._done))
        self._job_options = opts

    def _analysed(self, serial: int, analysis) -> None:
        if serial != self._serial or not self.session:
            return                                          # an older search, the settings have moved on
        self.session.apply(analysis, self._job_options)
        self.status.setText("  ".join(analysis.messages))
        self._refresh()

    def _analysis_failed(self, serial: int, text: str) -> None:
        if serial == self._serial:
            self.summary.setText("")
            self.status.setText(f"This sheet could not be searched: {text}")

    # ---- redraw ----------------------------------------------------------------------------------------------------
    def _refresh(self) -> None:
        s = self.session
        if not s or not s.analysis:
            return
        self.summary.setText(s.summary())
        self.panel.show_colours(s.analysis.background, s.analysis.cell_colour)
        self.title_label.setText(f"Source sheet: {s.path.name if s.path else ''}  ({s.image.width} x {s.image.height})")
        self.panel.update_selection(len(s.selected), s.selection_max_size())
        self.panel.show_note(s.message)
        self.view.update()
        self._schedule_output()

    # ---- the view --------------------------------------------------------------------------------------------------
    def _zoom(self, step: int) -> None:
        self.view.set_zoom(self.view.zoom + step)
        self.zoom_label.setText(f"{self.view.zoom}x")

    def _shape_clicked(self, x: int, y: int, ctrl: bool) -> None:
        s = self.session
        if not s or not s.analysis:
            return
        shape = s.shape_at(x, y)
        if shape is None:
            if not ctrl:
                s.select([])
                self._refresh()
            return
        if ctrl:
            s.toggle_selected(shape)
        else:
            s.toggle_shape(shape)
        self._refresh()

    def _rect_selected(self, x0: int, y0: int, x1: int, y1: int, ctrl: bool) -> None:
        s = self.session
        if not s or not s.analysis:
            return
        inside = []
        for sh in s.analysis.kept():
            cx, cy = (sh.box[0] + sh.box[2]) / 2, (sh.box[1] + sh.box[3]) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                inside.append(sh.box)
        s.select(inside, add=ctrl)
        self._refresh()

    def _pick_requested(self, which: str) -> None:
        self._pick_which = which
        self.view.set_picking(bool(which))
        self.hint.setText("Click a pixel on the sheet to choose the colour." if which else
                          "Click a shape to remove or restore it. Ctrl+click or drag to select sprites.")

    def _pixel_picked(self, x: int, y: int) -> None:
        s = self.session
        if not s or not s.analysis or not self._pick_which:
            return
        h, w = s.analysis.key.shape
        if not (0 <= x < w and 0 <= y < h):
            return
        which, key = self._pick_which, int(s.analysis.key[y, x])
        self._pick_which = ""
        self.view.set_picking(False)
        self.hint.setText("Click a shape to remove or restore it. Ctrl+click or drag to select sprites.")
        self.panel.set_colour_choice(which, key)

    # ---- the selected sprites --------------------------------------------------------------------------------------
    def _group(self) -> None:
        if self.session:
            self.session.group_selected()
            self._refresh()

    # ---- the output ------------------------------------------------------------------------------------------------
    def _build_output(self):
        s = self.session
        if not s or not s.analysis:
            return None
        result = build_sheets(s.analysis, s.groups, s.stem, s.options)
        nums = s.frame_numbers()
        refused = []
        for g in s.groups:
            if g.problem:
                frames = sorted(nums[x.box] for x in g.shapes)
                shown = ", ".join(str(n) for n in frames[:12]) + (" ..." if len(frames) > 12 else "")
                refused.append(f'{escape(g.problem)} Frame{"s" if len(frames) != 1 else ""}: '
                               f'<a href="f:{",".join(str(n) for n in frames)}" style="color:#ffd27a">{shown}</a> '
                               f'(click to select; click a shape to remove it).')
        return result, refused

    def _has_content(self) -> bool:
        return bool(self.session and self.session.analysis)

    # ---- clearing the selection ------------------------------------------------------------------------------------
    def clear_selection(self) -> None:
        """Esc: no selection, and no colour being picked."""
        for b in (self.panel.bg_pick, self.panel.cell_pick):
            if b.isChecked():
                b.setChecked(False)
        if self.session and self.session.selected:
            self.session.select([])
            self._refresh()

    _KEEPS_SELECTION = (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QComboBox, QTabBar)

    def eventFilter(self, obj, event) -> bool:
        """A left click on empty space anywhere in this window clears the selection. Clicks on a control, on a sprite
        (the source view deals with those itself) or with Ctrl held (adding to the selection) leave it alone."""
        if (event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton
                and isinstance(obj, QWidget) and obj.window() is self and self.session and self.session.selected
                and not (event.modifiers() & Qt.ControlModifier)):
            w = obj
            while w is not None and w is not self:
                if isinstance(w, self._KEEPS_SELECTION + (SourceView,)):
                    return False
                w = w.parentWidget()
            self.clear_selection()
        return False

    def _select_frames(self, numbers: list) -> None:
        """A frame number in a message was clicked: select those sprites and show the first."""
        s = self.session
        if not s or not s.analysis:
            return
        by_number = {n: box for box, n in s.frame_numbers().items()}
        boxes = [by_number[n] for n in numbers if n in by_number]
        s.select(boxes)
        if boxes:
            z = self.view.zoom
            x0, y0, x1, y1 = boxes[0]
            self.scroll.ensureVisible((x0 + x1) // 2 * z, (y0 + y1) // 2 * z, 80, 80)
        self._refresh()
