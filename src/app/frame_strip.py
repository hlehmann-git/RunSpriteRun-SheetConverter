"""The GIF's frames as numbered thumbnails: click one to keep or drop it, or (while picking a colour) click a pixel."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme

TARGET = 120           # a thumbnail is scaled up by a whole number to fit inside this
PAD = 6
TAG_H = 14


def checker(w: int, h: int) -> QImage:
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    for y in range(0, h, 8):
        for x in range(0, w, 8):
            p.fillRect(x, y, 8, 8, QColor(70, 70, 76) if (x // 8 + y // 8) % 2 else QColor(54, 54, 60))
    p.end()
    return img


class FrameStrip(QWidget):
    frame_clicked = Signal(int)                 # frame index
    pixel_picked = Signal(int, int, int)        # frame index, x, y (while picking)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = None
        self.zoom = 1
        self.picking = False
        self._images: list[QImage] = []
        self._width_hint = 600
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_session(self, session) -> None:
        self.session = session
        self._images = []
        if session and not session.error:
            w, h = session.sheet.size
            self.zoom = max(1, min(TARGET // w, TARGET // h, 8))
            for f in session.sheet.frames:
                rgba = np.ascontiguousarray(f.rgba)
                self._images.append(QImage(rgba.data, w, h, 4 * w, QImage.Format_RGBA8888).copy())
        self._relayout()

    def set_picking(self, on: bool) -> None:
        self.picking = on
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)

    # ---- layout ----------------------------------------------------------------------------------------------------
    def cell_size(self) -> QSize:
        if not self.session or self.session.error:
            return QSize(10, 10)
        w, h = self.session.sheet.size
        return QSize(w * self.zoom + 2 * PAD, h * self.zoom + 2 * PAD + TAG_H)

    def columns(self, width: int | None = None) -> int:
        return max(1, ((width or self.width() or self._width_hint)) // self.cell_size().width())

    def cell_rect(self, index: int) -> QRect:
        c, cs = self.columns(), self.cell_size()
        return QRect((index % c) * cs.width(), (index // c) * cs.height(), cs.width(), cs.height())

    def _relayout(self, width: int | None = None) -> None:
        n = len(self.session.sheet.frames) if self.session and not self.session.error else 0
        cs = self.cell_size()
        cols = self.columns(width)
        rows = max(1, -(-n // cols))
        self.setMinimumHeight(rows * cs.height())          # the scroll area sets the width
        self.update()

    def resizeEvent(self, event) -> None:
        if event.size().width() != event.oldSize().width():
            self._relayout(event.size().width())
        super().resizeEvent(event)

    def heightForWidth(self, w: int) -> int:
        n = len(self.session.sheet.frames) if self.session and not self.session.error else 0
        return max(1, -(-n // self.columns(w))) * self.cell_size().height()

    # ---- painting --------------------------------------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(event.rect(), QColor(theme.VIEW))
        s = self.session
        if not s or s.error or not self._images:
            return
        w, h = s.sheet.size
        z = self.zoom
        font = QFont(self.font())
        font.setPixelSize(11)
        p.setFont(font)
        box = s.result.box
        kept = {f.index for f in s.result.kept}
        for f in s.sheet.frames:
            r = self.cell_rect(f.index)
            if not r.intersects(event.rect()):
                continue
            pic = QRect(r.left() + PAD, r.top() + PAD, w * z, h * z)
            p.drawImage(pic, checker(w * z, h * z))
            p.drawImage(pic, self._images[f.index])
            if f.index in kept:
                if box is not None and (box[2] - box[0] + 1, box[3] - box[1] + 1) != (w, h):
                    p.setPen(QPen(QColor(80, 220, 255), 1))
                    p.drawRect(QRect(pic.left() + box[0] * z, pic.top() + box[1] * z,
                                     (box[2] - box[0] + 1) * z - 1, (box[3] - box[1] + 1) * z - 1))
                label, colour = str(f.index + 1), QColor(255, 160, 60)
            else:
                p.fillRect(pic, QColor(20, 20, 24, 170))
                p.setPen(QPen(QColor(0, 0, 0), 5))
                p.drawLine(pic.topLeft(), pic.bottomRight())
                p.drawLine(pic.topRight(), pic.bottomLeft())
                p.setPen(QPen(QColor(255, 60, 60), 3))
                p.drawLine(pic.topLeft(), pic.bottomRight())
                p.drawLine(pic.topRight(), pic.bottomLeft())
                label = f"{f.index + 1}  {'repeat' if f.repeat and s.options.remove_repeats else 'dropped'}"
                colour = QColor(150, 150, 150)
            tag = QRect(pic.left(), pic.bottom() + 2, max(24, p.fontMetrics().horizontalAdvance(label) + 8), TAG_H - 2)
            p.fillRect(tag, colour)
            p.setPen(QColor(0, 0, 0))
            p.drawText(tag, Qt.AlignCenter, label)

    # ---- mouse -----------------------------------------------------------------------------------------------------
    def _frame_at(self, pos: QPoint):
        s = self.session
        if not s or s.error:
            return None
        cs = self.cell_size()
        col, row = pos.x() // cs.width(), pos.y() // cs.height()
        if col >= self.columns():
            return None
        index = row * self.columns() + col
        return index if 0 <= index < len(s.sheet.frames) else None

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        pos = e.position().toPoint()
        index = self._frame_at(pos)
        if index is None:
            return
        if self.picking:
            r = self.cell_rect(index)
            x, y = (pos.x() - r.left() - PAD) // self.zoom, (pos.y() - r.top() - PAD) // self.zoom
            self.pixel_picked.emit(index, x, y)
        else:
            self.frame_clicked.emit(index)
