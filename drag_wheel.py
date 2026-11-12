"""X11 sürüklemelerinde görsel dönüştürme çarkını açar."""

from __future__ import annotations

from math import cos, radians, sin
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import (
    QColor, QCursor, QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent,
    QIcon, QPaintEvent, QPainter, QPainterPath, QPen, QRegion,
)
from PySide6.QtWidgets import QApplication, QWidget
from Xlib import X, display, error

from image_conversion import FORMATS

WHEEL_POSITIONS = ((0, 1), (2, 0), (2, 2))


def offers_file_copy(event: QDropEvent) -> bool:
    return bool(
        event.possibleActions() & Qt.DropAction.CopyAction and event.mimeData().hasUrls()
    )


def local_drop_paths(event: QDropEvent) -> tuple[Path, ...]:
    """Dosya listesini yalnız bırakma olayında ister."""
    if not offers_file_copy(event):
        return ()
    urls = event.mimeData().urls()
    if not all(url.isLocalFile() for url in urls):
        return ()
    paths = tuple(dict.fromkeys(Path(url.toLocalFile()) for url in urls))
    return paths if all(path.is_file() for path in paths) else ()


def accept_copy(event: QDropEvent) -> None:
    event.setDropAction(Qt.DropAction.CopyAction)
    event.accept()


class X11Drag:
    """Dosya içeriğini almadan XDND sahipliğini ve tuş durumunu okur."""

    def __init__(self) -> None:
        self.connection = display.Display()
        self.root = self.connection.screen().root
        self.selection = self.connection.intern_atom("XdndSelection")

    def state(self) -> tuple[bool, bool]:
        mask = self.root.query_pointer().mask
        dragging = bool(
            mask & X.Button1Mask and self.connection.get_selection_owner(self.selection)
        )
        return dragging, bool(mask & X.ShiftMask)

    def close(self) -> None:
        self.connection.close()


class DragWheel(QWidget):
    """Odak almadan açılan ve formatın üstüne bırakılan dosyaları ileten çark."""

    file_dropped = Signal(object, str)

    SIZE = 308
    OUTER_RADIUS = 151
    INNER_RADIUS = 77
    ANGLES = (90, 210, 330)
    SWEEP = 112

    def __init__(self, icon: QIcon) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setAccessibleName("Görsel dönüştürme çarkı")
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setMask(QRegion(self.rect(), QRegion.RegionType.Ellipse))
        self.icon = icon.pixmap(50, 50)
        self.center = QPointF(self.SIZE / 2, self.SIZE / 2)
        self.highlight: str | None = None
        self.shift_held = False
        self.sectors = {
            output_format: self.sector(angle)
            for output_format, angle in zip(FORMATS, self.ANGLES, strict=True)
        }

    def circle(self, radius: float) -> QRectF:
        return QRectF(
            self.center.x() - radius, self.center.y() - radius, radius * 2, radius * 2
        )

    def sector(self, angle: float) -> QPainterPath:
        start = angle - self.SWEEP / 2
        outer, inner = self.circle(self.OUTER_RADIUS), self.circle(self.INNER_RADIUS)
        path = QPainterPath()
        path.arcMoveTo(outer, start)
        path.arcTo(outer, start, self.SWEEP)
        path.arcTo(inner, start + self.SWEEP, -self.SWEEP)
        path.closeSubpath()
        return path

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#281323"))
        painter.drawEllipse(self.circle(self.OUTER_RADIUS + 2))
        font = painter.font()
        font.setPixelSize(17)
        font.setBold(True)
        painter.setFont(font)

        radius = (self.OUTER_RADIUS + self.INNER_RADIUS) / 2
        for (output_format, path), angle in zip(self.sectors.items(), self.ANGLES, strict=True):
            selected = self.highlight == output_format
            painter.setPen(QPen(QColor("#ff9b39" if selected else "#774a6d"), 1.5))
            painter.setBrush(QColor("#ff9b39" if selected else "#43263d"))
            painter.drawPath(path)
            painter.setPen(QColor("#341023" if selected else "#fff1db"))
            x = self.center.x() + radius * cos(radians(angle))
            y = self.center.y() - radius * sin(radians(angle))
            painter.drawText(QRectF(x - 34, y - 14, 68, 28), Qt.AlignmentFlag.AlignCenter, output_format)

        painter.setPen(QPen(QColor("#427c71"), 1.5))
        painter.setBrush(QColor("#203735"))
        painter.drawEllipse(self.circle(self.INNER_RADIUS - 6))
        painter.drawPixmap(QRect(129, 103, 50, 50), self.icon)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor("#fff1db"))
        hint = "Shift’i bırak\nFareyi tut" if self.shift_held else "Biçime bırak"
        painter.drawText(QRectF(84, 154, 140, 43), Qt.AlignmentFlag.AlignCenter, hint)

    def open_near_cursor(self) -> None:
        self.set_highlight(None)
        cursor = QCursor.pos()
        screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        x = cursor.x() - self.width() // 2
        y = cursor.y() - self.height() // 2
        self.move(QPoint(
            max(bounds.left(), min(x, bounds.right() - self.width() + 1)),
            max(bounds.top(), min(y, bounds.bottom() - self.height() + 1)),
        ))
        self.show()
        self.raise_()

    def update_hint(self, shift: bool) -> None:
        if self.shift_held != shift:
            self.shift_held = shift
            self.update()

    def set_highlight(self, output_format: str | None) -> None:
        if self.highlight != output_format:
            self.highlight = output_format
            self.update()

    def format_at(self, position: QPointF) -> str | None:
        return next(
            (output_format for output_format, sector in self.sectors.items() if sector.contains(position)),
            None,
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            self.set_highlight(self.format_at(event.position()))
        if offers_file_copy(event):
            accept_copy(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        output_format = self.format_at(event.position()) if event.mimeData().hasUrls() else None
        self.set_highlight(output_format)
        if output_format and offers_file_copy(event):
            accept_copy(event)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.set_highlight(None)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        output_format = self.format_at(event.position())
        paths = local_drop_paths(event) if output_format else ()
        if paths and output_format:
            accept_copy(event)
            self.hide()
            self.file_dropped.emit(paths, output_format)
        else:
            self.set_highlight(None)
            event.ignore()


class WheelMonitor(QTimer):
    """Shift ile açılan çarkı sürükleme sona erdiğinde kapatır."""

    def __init__(self, window: QWidget, wheel: DragWheel) -> None:
        super().__init__(window)
        self.wheel = wheel
        self.drag = X11Drag()
        self.enabled = True
        self.release_ticks = 0
        self.timeout.connect(self.poll)
        self.start(60)

    def poll(self) -> None:
        try:
            dragging, shift = self.drag.state()
        except (error.ConnectionClosedError, error.XError):
            self.stop()
            self.wheel.hide()
            return
        if dragging:
            self.release_ticks = 0
            if self.wheel.isVisible():
                self.wheel.update_hint(shift)
            elif self.enabled and shift:
                self.wheel.update_hint(shift=True)
                self.wheel.open_near_cursor()
        elif self.wheel.isVisible():
            self.release_ticks += 1
            # Fare bırakıldıktan sonra Qt'ye XDND bırakma olayını teslim etme süresi tanı.
            if self.release_ticks >= 3:
                self.wheel.hide()

    def shutdown(self) -> None:
        self.stop()
        self.wheel.close()
        self.drag.close()
