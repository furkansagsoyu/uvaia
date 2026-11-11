"""X11 sürüklemelerinde görsel dönüştürme çarkını açar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QDropEvent
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QPushButton, QWidget
from Xlib import X, display, error

from image_conversion import FORMATS

WHEEL_POSITIONS = ((0, 1), (2, 0), (2, 2))


def local_drop_path(event: QDropEvent) -> Path | None:
    """Tek bir yerel dosya ve kopyalama işlemi kabul eder."""
    urls = event.mimeData().urls()
    if event.possibleActions() & Qt.DropAction.CopyAction and len(urls) == 1:
        if urls[0].isLocalFile():
            return Path(urls[0].toLocalFile())
    return None


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
    """Odak almadan açılan ve formatın üstüne bırakılan dosyayı ileten çark."""

    file_dropped = Signal(object, str)

    def __init__(self, stylesheet: str) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setStyleSheet(stylesheet)
        layout = QGridLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        center = QLabel("Bir biçime bırak")
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(center, 1, 1)
        for output_format, position in zip(FORMATS, WHEEL_POSITIONS, strict=True):
            target = QPushButton(output_format)
            target.setProperty("format", True)
            target.setProperty("outputFormat", output_format)
            target.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout.addWidget(target, *position)

    def open_near_cursor(self) -> None:
        self.adjustSize()
        cursor = QCursor.pos()
        screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        x = cursor.x() - self.width() // 2
        y = cursor.y() + 24
        if y + self.height() > bounds.bottom():
            y = cursor.y() - self.height() - 24
        self.move(
            QPoint(
                max(bounds.left(), min(x, bounds.right() - self.width() + 1)),
                max(bounds.top(), y),
            )
        )
        self.show()
        self.raise_()

    def dragEnterEvent(self, event: QDropEvent) -> None:
        if local_drop_path(event) is not None:
            accept_copy(event)

    def dragMoveEvent(self, event: QDropEvent) -> None:
        if self.format_at(event) and local_drop_path(event) is not None:
            accept_copy(event)

    def dropEvent(self, event: QDropEvent) -> None:
        source = local_drop_path(event)
        output_format = self.format_at(event)
        if source is not None and source.is_file() and output_format:
            accept_copy(event)
            self.hide()
            self.file_dropped.emit(source, output_format)

    def format_at(self, event: QDropEvent) -> str | None:
        target = self.childAt(event.position().toPoint())
        return target.property("outputFormat") if target else None


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
            if self.enabled and shift and not self.wheel.isVisible():
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
