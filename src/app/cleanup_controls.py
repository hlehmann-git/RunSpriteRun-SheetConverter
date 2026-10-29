"""The Colours section shared by the sprite sheet window and the animation window: the Clean up / Reduce colours
switch, its strength and the line saying what it did. The same merge, at the same strengths, is offered for any
file: a lossy WebP is offered it pre-ticked, as clean-up for its compression smudging; anything else is offered
it unticked, as an optional way to reduce an already-exact palette."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..core.colours import DEFAULT_STRENGTH, STRENGTHS


class CleanupControls(QWidget):
    changed = Signal(object)            # the strength name, or None when the switch is off

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        row = QHBoxLayout()
        self.switch = QCheckBox("Clean up colours")
        row.addWidget(self.switch, 1)
        row.addWidget(QLabel("Strength"))
        self.strength = QComboBox()
        for name in STRENGTHS:
            self.strength.addItem(name, name)
        self.strength.setCurrentIndex(self.strength.findData(DEFAULT_STRENGTH))
        self.strength.setToolTip("Very low keeps the most shades; Very high merges the most, for heavily compressed "
                                 "files. Each step lets colours a little further apart merge.")
        row.addWidget(self.strength)
        lay.addLayout(row)
        self.note = QLabel("")
        self.note.setObjectName("dim")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.switch.toggled.connect(self._emit)
        self.strength.currentIndexChanged.connect(self._emit)
        self.set_file(False, None, "")

    def value(self) -> str | None:
        return self.strength.currentData() if self.switch.isChecked() else None

    def set_file(self, lossy: bool, strength: str | None, note: str) -> None:
        """Show a newly opened file's state without sending `changed`. Offered for any file: "Clean up colours"
        for a lossy WebP (its smudged compression), "Reduce colours" for anything else (an already-exact
        palette, merged down by choice)."""
        for w in (self.switch, self.strength):
            w.blockSignals(True)
        self.switch.setText("Clean up colours" if lossy else "Reduce colours")
        self.switch.setToolTip(
            "Merge the smudged colours of a lossy WebP back into a small palette. Only colours already in the "
            "picture are used." if lossy else
            "Merge colours that are close in value into a smaller palette. Only colours already in the picture "
            "are used.")
        self.switch.setChecked(bool(strength))
        if strength:
            self.strength.setCurrentIndex(self.strength.findData(strength))
        for w in (self.switch, self.strength):
            w.blockSignals(False)
        self.strength.setEnabled(bool(strength))
        self.note.setText(note)

    def set_note(self, text: str) -> None:
        self.note.setText(text)

    def _emit(self, *_):
        self.strength.setEnabled(self.switch.isChecked())
        self.changed.emit(self.value())
