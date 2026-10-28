"""The source sheet on screen: the picture at a whole-number zoom, an outline and a frame number on every sprite
(coloured by size group), a red cross on removed shapes (when Show removed shapes is on; otherwise removed shapes are painted out). Clicks are reported; nothing is decided here."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .session import Session, group_colour
from . import theme

MAX_ZOOM = 8
DRAG_PIXELS = 4


def to_qimage(img) -> QImage:
    rgba = np.ascontiguousarray(np.asarray(img.convert("RGBA")))
    h, w = rgba.shape[:2]
    q = QImage(rgba.data, w, h, 4 * w, QImage.Format_RGBA8888)
    return q.copy()                                        # own the memory


def around(arr: np.ndarray, box, w: int, h: int) -> np.ndarray:
    """The commonest colour on the one-pixel ring just outside a box: what the shape sits on (a panel's colour
    for text in a panel, the sheet's background for a frame line)."""
    x0, y0, x1, y1 = box
    xa, ya, xb, yb = max(0, x0 - 1), max(0, y0 - 1), min(w - 1, x1 + 1), min(h - 1, y1 + 1)
    ring = np.concatenate([arr[ya, xa:xb + 1], arr[yb, xa:xb + 1], arr[ya:yb + 1, xa], arr[ya:yb + 1, xb]])
    values, counts = np.unique(ring.reshape(-1, 4), axis=0, return_counts=True)
    return values[int(np.argmax(counts))]


def painted_out(image, analysis, removed) -> QImage:
    """The sheet with the removed shapes painted over: a loose shape's own pixels take the colour around it, an
    empty cell (or a table box) becomes the sheet's background."""
    arr = np.array(image.convert("RGBA"))

    def rgba(key: int):
        return (0, 0, 0, 0) if key < 0 else ((key >> 16) & 255, (key >> 8) & 255, key & 255, 255)

    original = arr.copy()
    h, w = arr.shape[:2]
    for x in removed:
        x0, y0, x1, y1 = x.box
        region = arr[y0:y1 + 1, x0:x1 + 1]
        if x.kind in ("cell", "grid"):
            region[:] = rgba(analysis.background)
        else:
            region[x.mask] = around(original, x.box, w, h)
    return QImage(np.ascontiguousarray(arr).data, w, h, 4 * w, QImage.Format_RGBA8888).copy()


BIG_SHAPE = 128           # removed shapes wider or taller than any sprite get a dashed outline instead of a cross


class SourceView(QWidget):
    shape_clicked = Signal(int, int, bool)       # sheet x, y, ctrl held
    pixel_picked = Signal(int, int)              # sheet x, y (while in pick mode)
    rect_selected = Signal(int, int, int, int, bool)   # x0, y0, x1, y1 (sheet pixels), ctrl held
    empty_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session: Session | None = None
        self.qimage: QImage | None = None
        self.zoom = 1
        self.show_removed = False             # removed shapes are painted out unless switched on (then: red cross)
        self._clean: QImage | None = None     # the picture with the removed shapes painted out, and what it was made from
        self._clean_key = None
        self.picking = False
        self._press: QPoint | None = None
        self._drag: QRect | None = None
        self._ctrl = False
        self.setMouseTracking(False)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    # ---- content ---------------------------------------------------------------------------------------------------
    def set_session(self, session: Session | None, zoom: int | None = None) -> None:
        self.session = session
        self.qimage = to_qimage(session.image) if session else None
        if zoom:
            self.zoom = max(1, min(MAX_ZOOM, zoom))
        self._resize()
        self.update()

    def set_zoom(self, zoom: int) -> None:
        self.zoom = max(1, min(MAX_ZOOM, int(zoom)))
        self._resize()
        self.update()

    def _resize(self) -> None:
        if self.qimage is None:
            self.setFixedSize(QSize(10, 10))
        else:
            self.setFixedSize(self.qimage.width() * self.zoom, self.qimage.height() * self.zoom)

    def set_picking(self, on: bool) -> None:
        self.picking = on
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)

    def to_sheet(self, p: QPoint) -> tuple[int, int]:
        return p.x() // self.zoom, p.y() // self.zoom

    # ---- painting --------------------------------------------------------------------------------------------------
    def _picture(self) -> QImage:
        """The sheet as shown: with Show removed shapes off, every removed shape (the program's and the user's) is
        painted out in the colour around it, so only the sprites being kept are left. The file is not changed."""
        s = self.session
        if self.show_removed or s is None or s.analysis is None:
            return self.qimage
        removed = [x for x in s.analysis.shapes if x.removed]
        key = (id(s.analysis), id(s.image), tuple((x.box, x.kind) for x in removed))
        if key != self._clean_key:
            self._clean_key, self._clean = key, painted_out(s.image, s.analysis, removed)
        return self._clean

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(event.rect(), QColor(theme.VIEW))
        if self.qimage is None:
            return
        z = self.zoom
        p.drawImage(QRect(0, 0, self.qimage.width() * z, self.qimage.height() * z), self._picture())
        s = self.session
        if s is None or s.analysis is None:
            return
        numbers = s.frame_numbers()
        font = QFont(self.font())
        font.setPixelSize(10)
        p.setFont(font)
        clip = event.rect()
        for shape in s.analysis.shapes:
            x0, y0, x1, y1 = shape.box
            r = QRect(x0 * z, y0 * z, (x1 - x0 + 1) * z, (y1 - y0 + 1) * z)
            if not r.adjusted(-3, -3, 3, 3).intersects(clip):
                continue
            if shape.removed:
                if not self.show_removed:
                    continue                                       # painted out of the picture (see _picture)
                if shape.width > BIG_SHAPE or shape.height > BIG_SHAPE:     # a frame line or big picture: outline only,
                    p.setPen(QPen(QColor(255, 60, 60, 150), 1, Qt.DashLine))  # no cross from corner to corner
                    p.drawRect(r.adjusted(0, 0, -1, -1))
                    continue
                p.fillRect(r, QColor(220, 40, 40, 70))
                p.setPen(QPen(QColor(0, 0, 0), 5))                     # a dark edge so the cross shows on any colour
                p.drawLine(r.topLeft(), r.bottomRight())
                p.drawLine(r.topRight(), r.bottomLeft())
                p.setPen(QPen(QColor(255, 60, 60), 3))
                p.drawLine(r.topLeft(), r.bottomRight())
                p.drawLine(r.topRight(), r.bottomLeft())
                p.setPen(QPen(QColor(255, 60, 60), 2))
                p.drawRect(r.adjusted(1, 1, -2, -2))
                continue
            gi = s.group_of(shape)
            c = QColor(*group_colour(max(gi, 0)))
            selected = shape.box in s.selected
            p.setPen(QPen(QColor(255, 255, 255) if selected else c, 3 if selected else 1))
            p.drawRect(r.adjusted(0, 0, -1, -1))
            n = str(numbers.get(shape.box, ""))
            w = p.fontMetrics().horizontalAdvance(n) + 4
            tag = QRect(r.left(), r.top(), w, 12)
            p.fillRect(tag, c)
            p.setPen(QColor(0, 0, 0))
            p.drawText(tag, Qt.AlignCenter, n)
        if self._drag is not None:
            p.setPen(QPen(QColor(255, 255, 255), 1, Qt.DashLine))
            p.drawRect(self._drag)

    # ---- mouse -----------------------------------------------------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self.qimage is None:
            return
        self._press = e.position().toPoint()
        self._ctrl = bool(e.modifiers() & Qt.ControlModifier)
        self._drag = None

    def mouseMoveEvent(self, e) -> None:
        if self._press is None or self.picking:
            return
        cur = e.position().toPoint()
        if (cur - self._press).manhattanLength() >= DRAG_PIXELS:
            self._drag = QRect(self._press, cur).normalized()
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self._press is None:
            return
        press, drag = self._press, self._drag
        self._press, self._drag = None, None
        self.update()
        if self.picking:
            x, y = self.to_sheet(press)
            self.pixel_picked.emit(x, y)
            return
        if drag is not None:
            x0, y0 = self.to_sheet(drag.topLeft())
            x1, y1 = self.to_sheet(drag.bottomRight())
            self.rect_selected.emit(x0, y0, x1, y1, self._ctrl)
            return
        x, y = self.to_sheet(press)
        self.shape_clicked.emit(x, y, self._ctrl)
