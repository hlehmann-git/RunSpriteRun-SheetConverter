"""The Adjust panel: every setting that changes what counts as a sprite and how the boxes are chosen (PRD section 5),
and what to do with the selected sprites. It builds an Options and says when it changed."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QRadioButton,
                               QSlider, QSpinBox, QVBoxLayout)

from .cleanup_controls import CleanupControls
from ..core.detect import Options, rgb_of

ANALYSIS_FIELDS = ("join_gap", "min_shape", "max_shape", "remove_text", "keep_empty", "background", "cell_colour",
                   "cells_off")


def needs_analysis(a: Options, b: Options) -> bool:
    """True when the difference between two sets of options means the sheet must be searched again."""
    return any(getattr(a, f) != getattr(b, f) for f in ANALYSIS_FIELDS)


def _section(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setObjectName("section")
    return lab


class Swatch(QLabel):
    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 20)
        self.set_key(None)

    def set_key(self, key: int | None) -> None:
        if key is None:
            self.setStyleSheet("border: 1px dashed #6a6e7c; border-radius: 3px; background: transparent;")
        elif key < 0:
            self.setStyleSheet("border: 1px solid #e6e8ee; border-radius: 3px; background: qlineargradient("
                               "x1:0,y1:0,x2:1,y2:1,stop:0 #888,stop:0.5 #ccc,stop:1 #888);")
        else:
            r, g, b = rgb_of(key)
            self.setStyleSheet(f"border: 1px solid #e6e8ee; border-radius: 3px; background: rgb({r},{g},{b});")


class AdjustPanel(QFrame):
    options_changed = Signal()
    pick_requested = Signal(str)          # "background" or "cell"
    group_requested = Signal()
    merge_requested = Signal()
    split_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._options = Options()
        self._busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(3)
        head = QHBoxLayout()
        t = QLabel("Adjust")
        t.setObjectName("head")
        d = QLabel("The outlines redraw at once")
        d.setObjectName("dim")
        head.addWidget(t)
        head.addWidget(d)
        head.addStretch()
        lay.addLayout(head)

        lay.addWidget(_section("Colours"))
        self.cleanup = CleanupControls()
        lay.addWidget(self.cleanup)
        lay.addWidget(_section("Box sizes"))
        self.estimate = QRadioButton("Estimate appropriate sprite box sizes")
        self.same = QRadioButton("Fit into the same size sprite box for all sprites")
        self.estimate.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.estimate)
        grp.addButton(self.same)
        lay.addWidget(self.estimate)
        lay.addWidget(self.same)
        self.tolerance, self.tolerance_text = self._slider(lay, "Size tolerance", 0, 32, 8)

        lay.addWidget(_section("What counts as a sprite"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Background colour"), 1)
        self.bg_swatch = Swatch()
        self.bg_text = QLabel("Transparent")
        self.bg_text.setObjectName("dim")
        self.bg_pick = QPushButton("Pick")
        self.bg_pick.setCheckable(True)
        self.bg_auto = QPushButton("Auto")
        for w in (self.bg_swatch, self.bg_text):
            row.addWidget(w)
        row.addStretch()
        row.addWidget(self.bg_pick)
        row.addWidget(self.bg_auto)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Cell colour"), 1)
        self.cell_swatch = Swatch()
        self.cell_text = QLabel("None found")
        self.cell_text.setObjectName("dim")
        self.cell_pick = QPushButton("Pick")
        self.cell_pick.setCheckable(True)
        self.cell_auto = QPushButton("Auto")
        self.cell_off = QPushButton("Off")
        self.cell_off.setCheckable(True)
        for w in (self.cell_swatch, self.cell_text):
            row.addWidget(w)
        row.addStretch()
        for w in (self.cell_pick, self.cell_auto, self.cell_off):
            row.addWidget(w)
        lay.addLayout(row)
        self.join_gap, self.join_text = self._slider(lay, "Join gap", 0, 16, 3)
        self.remove_text = QCheckBox("Remove text and palettes")
        self.remove_text.setChecked(True)
        lay.addWidget(self.remove_text)
        row = QHBoxLayout()
        row.addWidget(QLabel("Ignore shapes smaller than"))
        self.min_shape = QSpinBox()
        self.min_shape.setRange(1, 64)
        self.min_shape.setValue(4)
        self.min_shape.setSuffix(" px")
        self.min_shape.setToolTip("A shape with fewer pixels than this is a speck and is ignored.")
        row.addWidget(self.min_shape)
        row.addWidget(QLabel("larger than"))
        self.max_shape = QSpinBox()
        self.max_shape.setRange(8, 512)
        self.max_shape.setValue(128)
        self.max_shape.setSuffix(" px")
        self.max_shape.setToolTip("A shape wider or taller than this is a picture, not a sprite, and is removed.")
        row.addWidget(self.max_shape)
        row.addStretch()
        lay.addLayout(row)

        lay.addWidget(_section("Placing sprites in their boxes"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Vertical placement"))
        self.bottom = QPushButton("Bottom")
        self.centre = QPushButton("Centre")
        for b in (self.bottom, self.centre):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            row.addWidget(b)
        self.bottom.setChecked(True)
        self.keep_empty = QCheckBox("Keep empty cells")
        row.addSpacing(14)
        row.addWidget(self.keep_empty)
        row.addStretch()
        lay.addLayout(row)

        box = QFrame()
        box.setObjectName("selbox")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(5)
        head = QHBoxLayout()
        self.selected_head = QLabel("Selected sprites: none")
        self.selected_head.setObjectName("head")
        hint = QLabel("Ctrl+click, or drag a rectangle. Esc clears.")
        hint.setObjectName("dim")
        head.addWidget(self.selected_head)
        head.addWidget(hint)
        head.addStretch()
        bl.addLayout(head)
        self.group_btn = QPushButton()
        self.group_btn.setObjectName("primary")
        self.group_btn.setMinimumHeight(40)
        self.group_btn.setToolTip("Puts all the selected sprites, from any size group, on one sheet with a box as wide "
                                  "as the widest and as tall as the tallest of them.")
        inner = QHBoxLayout(self.group_btn)
        inner.setContentsMargins(8, 2, 8, 2)
        self.group_label = QLabel("Group the selected sprites into one box")
        self.group_label.setWordWrap(True)
        self.group_label.setAlignment(Qt.AlignCenter)
        self.group_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        inner.addWidget(self.group_label)
        bl.addWidget(self.group_btn)
        expl = QLabel("Puts them on one sheet. The box is as wide as the widest and as tall as the tallest.")
        expl.setObjectName("dim")
        expl.setWordWrap(True)
        bl.addWidget(expl)
        mrow = QHBoxLayout()
        self.merge_btn = QPushButton("Merge into one sprite box")
        self.merge_btn.setToolTip("The selected pieces become one sprite whose box covers them all (for an effect "
                                  "such as sparkles whose pieces do not touch).")
        self.split_btn = QPushButton("Split")
        self.split_btn.setToolTip("Split a merged sprite back into its pieces.")
        mrow.addWidget(self.merge_btn, 1)
        mrow.addWidget(self.split_btn)
        bl.addLayout(mrow)
        self.note = QLabel("")
        self.note.setObjectName("orange")
        self.note.setWordWrap(True)
        bl.addWidget(self.note)
        lay.addSpacing(6)
        lay.addWidget(box)
        lay.addStretch()

        for sig in (self.estimate.toggled, self.tolerance.valueChanged, self.join_gap.valueChanged,
                    self.remove_text.toggled, self.min_shape.valueChanged, self.max_shape.valueChanged,
                    self.bottom.toggled, self.keep_empty.toggled):
            sig.connect(self._changed)
        self.bg_pick.toggled.connect(lambda on: self._pick("background", on))
        self.cell_pick.toggled.connect(lambda on: self._pick("cell", on))
        self.bg_auto.clicked.connect(self._bg_auto)
        self.cell_auto.clicked.connect(self._cell_auto)
        self.cell_off.toggled.connect(self._cell_off)
        self.group_btn.clicked.connect(self.group_requested)
        self.merge_btn.clicked.connect(self.merge_requested)
        self.split_btn.clicked.connect(self.split_requested)
        self.set_enabled_for_sheet(False)

    # ---- helpers ---------------------------------------------------------------------------------------------------
    def _slider(self, lay, label: str, lo: int, hi: int, value: int):
        row = QHBoxLayout()
        lab = QLabel(label)
        lab.setMinimumWidth(130)
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(value)
        val = QLabel(f"{value} px")
        val.setMinimumWidth(40)
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        s.valueChanged.connect(lambda v, val=val: val.setText(f"{v} px"))
        row.addWidget(lab)
        row.addWidget(s, 1)
        row.addWidget(val)
        lay.addLayout(row)
        return s, val

    def set_enabled_for_sheet(self, on: bool) -> None:
        for w in (self.estimate, self.same, self.tolerance, self.bg_pick, self.bg_auto, self.cell_pick, self.cell_auto,
                  self.cell_off, self.join_gap, self.remove_text, self.min_shape, self.max_shape, self.bottom,
                  self.centre, self.keep_empty):
            w.setEnabled(on)
        self.update_selection(0, None)

    # ---- reading and writing the options ---------------------------------------------------------------------------
    def options(self) -> Options:
        o = self._options
        return replace(o, box_mode="estimate" if self.estimate.isChecked() else "same",
                       size_tolerance=self.tolerance.value(), join_gap=self.join_gap.value(),
                       remove_text=self.remove_text.isChecked(), min_shape=self.min_shape.value(),
                       max_shape=self.max_shape.value(), vertical="bottom" if self.bottom.isChecked() else "centre",
                       keep_empty=self.keep_empty.isChecked(), cells_off=self.cell_off.isChecked())

    def set_colour_choice(self, which: str, key: int | None) -> None:
        """The user picked a colour on the sheet (key -1 = transparent) or went back to automatic (None)."""
        if which == "background":
            self._options = replace(self._options, background=key)
        else:
            self._options = replace(self._options, cell_colour=key)
            if key is not None and self.cell_off.isChecked():
                self.cell_off.blockSignals(True)
                self.cell_off.setChecked(False)
                self.cell_off.blockSignals(False)
        self.bg_pick.setChecked(False)
        self.cell_pick.setChecked(False)
        self.options_changed.emit()

    def reset_colours(self) -> None:
        """A new sheet: the background and cell colour are found again (nothing picked)."""
        self._options = replace(self._options, background=None, cell_colour=None)
        for b in (self.bg_pick, self.cell_pick):
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)

    def show_colours(self, background: int | None, cell: int | None) -> None:
        self.bg_swatch.set_key(background)
        self.bg_text.setText("" if background is None else "Transparent" if background < 0
                             else "#%02X%02X%02X" % rgb_of(background))
        off = self.cell_off.isChecked()
        self.cell_swatch.set_key(None if off else cell)
        self.cell_text.setText("Off" if off else "None found" if cell is None else "#%02X%02X%02X" % rgb_of(cell))

    def update_selection(self, count: int, max_size: tuple[int, int] | None = None, can_split: bool = False) -> None:
        on = count > 0
        self.merge_btn.setEnabled(count > 1)
        self.split_btn.setEnabled(can_split)
        self.selected_head.setText(f"Selected sprites: {count if on else 'none'}")
        self.group_btn.setEnabled(on)
        self.group_label.setText(f"Group the {count} selected sprite{'s' if count != 1 else ''} into one box of "
                                 f"{max_size[0]} x {max_size[1]}" if on and max_size
                                 else "Group the selected sprites into one box")
        self.group_label.setStyleSheet("color: white;" if on else "color: #6a6e7c;")

    def show_note(self, text: str) -> None:
        self.note.setText(text)

    # ---- slots -----------------------------------------------------------------------------------------------------
    def _changed(self, *_):
        self.options_changed.emit()

    def _pick(self, which: str, on: bool) -> None:
        if on:
            other = self.cell_pick if which == "background" else self.bg_pick
            other.blockSignals(True)
            other.setChecked(False)
            other.blockSignals(False)
        self.pick_requested.emit(which if on else "")

    def _bg_auto(self) -> None:
        self.set_colour_choice("background", None)

    def _cell_auto(self) -> None:
        self.cell_off.blockSignals(True)
        self.cell_off.setChecked(False)
        self.cell_off.blockSignals(False)
        self.set_colour_choice("cell", None)

    def _cell_off(self, on: bool) -> None:
        self.options_changed.emit()
