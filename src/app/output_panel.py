"""The output preview: one tab for each sheet that will be written, shown exactly as it will be saved, with the
messages about it, the folder and the Save Sheets button."""
from __future__ import annotations

from pathlib import Path

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QTabBar, QVBoxLayout, QWidget)

from ..core.output import OutputSheet, Result
from ..io.save import default_folder
from .source_view import to_qimage


class ElidedLabel(QLabel):
    """One line of text; if it is too long the middle is replaced by "..." (the full text is the tooltip)."""

    def __init__(self, text: str = ""):
        super().__init__()
        self._full = ""
        self.setMinimumWidth(60)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self.update()

    def full_text(self) -> str:
        return self._full

    def displayed_text(self) -> str:
        m = self.contentsMargins()
        room = self.width() - m.left() - m.right() - 14           # the padding of the box
        return self.fontMetrics().elidedText(self._full, Qt.ElideMiddle, max(10, room))

    def paintEvent(self, event) -> None:
        self.setText(self.displayed_text())
        super().paintEvent(event)


class OutputPanel(QFrame):
    frames_clicked = Signal(list)         # frame numbers named in a message
    save_clicked = Signal()
    browse_clicked = Signal()
    tick_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.sheets: list[OutputSheet] = []
        self.folder: Path = default_folder()
        self._zoom = 1
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(10)

        left = QVBoxLayout()
        top = QHBoxLayout()
        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setMinimumWidth(240)
        self.tabs.setMinimumHeight(28)
        self.tabs.currentChanged.connect(self._show_tab)
        top.addWidget(self.tabs, 1)
        top.setSpacing(6)
        self.tick = QCheckBox("Save this sheet")
        self.tick.toggled.connect(self._ticked)
        top.addWidget(self.tick)
        self.zoom_out = QPushButton("-")
        self.zoom_in = QPushButton("+")
        self.zoom_label = QLabel("1x")
        for b in (self.zoom_out, self.zoom_in):
            b.setFixedWidth(26)
        top.addWidget(self.zoom_out)
        top.addWidget(self.zoom_label)
        top.addWidget(self.zoom_in)
        left.addLayout(top)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.picture)
        self.scroll.setWidgetResizable(False)
        self.scroll.setMinimumHeight(120)
        left.addWidget(self.scroll, 1)
        self.info = QLabel("")
        self.info.setObjectName("dim")
        self.info.setWordWrap(True)
        self.info.setMinimumHeight(30)
        left.addWidget(self.info)
        outer.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(4)
        hint = QLabel("Output preview: each sheet exactly as it will be saved")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        right.addWidget(hint)
        self.messages = QLabel("")
        self.messages.setObjectName("orange")
        self.messages.setWordWrap(True)
        self.messages.setTextFormat(Qt.RichText)
        self.messages.setOpenExternalLinks(False)
        self.messages.linkActivated.connect(self._link)
        self.messages.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        right.addWidget(self.messages, 1)
        right.addWidget(self._dim("Save to folder"))
        row = QHBoxLayout()
        self.folder_label = ElidedLabel(str(self.folder))
        self.folder_label.setObjectName("folder")
        self.browse = QPushButton("Browse...")
        self.browse.clicked.connect(self.browse_clicked)
        row.addWidget(self.folder_label, 1)
        row.addWidget(self.browse)
        right.addLayout(row)
        self.save_button = QPushButton("Save Sheets")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_clicked)
        right.addWidget(self.save_button)
        self.saved = QLabel("Nothing is written until you click Save Sheets. The original file is never changed.")
        self.saved.setObjectName("dim")
        self.saved.setWordWrap(True)
        right.addWidget(self.saved)
        side = QWidget()
        side.setLayout(right)
        side.setFixedWidth(330)
        outer.addWidget(side)

        self.zoom_out.clicked.connect(lambda: self._set_zoom(self._zoom - 1))
        self.zoom_in.clicked.connect(lambda: self._set_zoom(self._zoom + 1))
        self.show_result(None, None)

    @staticmethod
    def _dim(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("dim")
        return lab

    # ---- what is shown ---------------------------------------------------------------------------------------------
    def set_folder(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.folder_label.set_full_text(str(self.folder))

    def show_result(self, result: Result | None, ticks: dict[str, bool] | None, keep: str = "",
                    refused_html: list[str] | None = None) -> None:
        """Show the sheets of a new build. `ticks` keeps the choices already made (by file name)."""
        self.sheets = list(result.sheets) if result else []
        for s in self.sheets:
            if ticks and s.file_name in ticks:
                s.save = ticks[s.file_name]
        self._result = result
        self._refused_html = list(refused_html) if refused_html is not None else None
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for s in self.sheets:
            self.tabs.addTab(f"{s.width} x {s.height}{f' part {s.part}' if s.part > 1 else ''}  -  "
                             f"{s.count} frame{'s' if s.count != 1 else ''}")
        index = next((i for i, s in enumerate(self.sheets) if s.file_name == keep), 0)
        if self.sheets:
            self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        self._show_tab(index if self.sheets else -1)
        self._update_save_button()

    def _show_tab(self, index: int) -> None:
        r = getattr(self, "_result", None)
        refused = self._refused_html if getattr(self, "_refused_html", None) is not None else (r.refused if r else [])
        global_msgs = (list(r.messages) + list(refused)) if r else []
        if not (0 <= index < len(self.sheets)):
            self.picture.clear()
            self.picture.resize(10, 10)
            self.tick.setEnabled(False)
            self.info.setText("" if r is None else "No sheets can be made from what is selected.")
            self.messages.setText("<br>".join(x if x.startswith("<") else escape(x) for x in global_msgs))
            return
        s = self.sheets[index]
        self.tick.setEnabled(True)
        self.tick.blockSignals(True)
        self.tick.setChecked(s.save)
        self.tick.blockSignals(False)
        self._draw(s)
        per = min(10, s.count)
        rows = -(-s.count // 10)
        self.info.setText(f"{s.file_name}  -  frame size {s.width} x {s.height}  -  {per} per row  -  {rows} row{'s' if rows != 1 else ''}"
                          f"  -  {s.colours} colours used")
        mine = [escape(m) for m in s.messages]
        gm = [escape(m) if not m.startswith("<") else m for m in (r.messages if r else [])]
        refused_part = [x if x.startswith("<") else escape(x) for x in refused]
        self.messages.setText("<br>".join(mine + gm + refused_part))

    def _draw(self, s: OutputSheet) -> None:
        q = to_qimage(s.image)
        pm = QPixmap.fromImage(q).scaled(q.width() * self._zoom, q.height() * self._zoom, Qt.IgnoreAspectRatio,
                                         Qt.FastTransformation)
        self.picture.setPixmap(pm)
        self.picture.resize(pm.size())

    def _set_zoom(self, z: int) -> None:
        self._zoom = max(1, min(4, z))
        self.zoom_label.setText(f"{self._zoom}x")
        i = self.tabs.currentIndex()
        if 0 <= i < len(self.sheets):
            self._draw(self.sheets[i])

    def _link(self, href: str) -> None:
        if href.startswith("f:"):
            self.frames_clicked.emit([int(v) for v in href[2:].split(",") if v.isdigit()])

    def current_name(self) -> str:
        i = self.tabs.currentIndex()
        return self.sheets[i].file_name if 0 <= i < len(self.sheets) else ""

    def ticks(self) -> dict[str, bool]:
        return {s.file_name: s.save for s in self.sheets}

    def _ticked(self, on: bool) -> None:
        i = self.tabs.currentIndex()
        if 0 <= i < len(self.sheets):
            self.sheets[i].save = on
            self._update_save_button()
            self.tick_changed.emit()

    def _update_save_button(self) -> None:
        n = sum(1 for s in self.sheets if s.save)
        self.save_button.setText(f"Save Sheets ({n} of {len(self.sheets)})" if self.sheets else "Save Sheets")
        self.save_button.setEnabled(n > 0)

    def show_saved(self, text: str) -> None:
        self.saved.setText(text)
