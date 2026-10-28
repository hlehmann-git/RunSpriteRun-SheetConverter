"""The Colours section shared by the sprite sheet window and the animation window: the Clean up colours switch, its
strength and the line saying what it did. It only matters for a lossy WebP; for any other file it is greyed out."""
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
        self.switch.setToolTip("Merge the smudged colours of a lossy WebP back into a small palette. Only colours "
                               "already in the picture are used.")
        row.addWidget(self.switch, 1)
        row.addWidget(QLabel("Strength"))
        self.strength = QComboBox()
        for name in STRENGTHS:
            self.strength.addItem(name, name)
        self.strength.setCurrentIndex(self.strength.findData(DEFAULT_STRENGTH))
        self.strength.setToolTip("Low keeps more shades; High merges more, for heavily compressed files.")
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
        """Show a newly opened file's state without sending `changed`."""
        for w in (self.switch, self.strength):
            w.blockSignals(True)
        self.switch.setChecked(bool(strength))
        if strength:
            self.strength.setCurrentIndex(self.strength.findData(strength))
        for w in (self.switch, self.strength):
            w.blockSignals(False)
        self.switch.setEnabled(lossy)
        self.strength.setEnabled(lossy and bool(strength))
        self.note.setText(note)

    def set_note(self, text: str) -> None:
        self.note.setText(text)

    def _emit(self, *_):
        self.strength.setEnabled(self.switch.isEnabled() and self.switch.isChecked())
        self.changed.emit(self.value())
