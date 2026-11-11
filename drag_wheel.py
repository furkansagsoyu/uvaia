"""X11 sürüklemelerinde görsel dönüştürme çarkını açar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QPushButton, QWidget
from Xlib import X, display, error

from image_conversion import FORMATS

WHEEL_POSITIONS = ((0, 1), (2, 0), (2, 2))


def offers_file_copy(event: QDropEvent) -> bool:
    return bool(
        event.possibleActions() & Qt.DropAction.CopyAction and event.mimeData().hasUrls()
    )


def local_drop_path(event: QDropEvent) -> Path | None:
    """Dosya listesini yalnız bırakma olayında ister."""
    if not offers_file_copy(event):
        return None
    urls = event.mimeData().urls()
    if len(urls) == 1 and urls[0].isLocalFile():
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
        self.hint = QLabel("Shift’i bırak, fareyi tut")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setMinimumWidth(self.hint.sizeHint().width())
        layout.addWidget(self.hint, 1, 0, 1, 3)
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

    def update_hint(self, shift: bool) -> None:
        message = "Shift’i bırak, fareyi tut" if shift else "Bir biçime bırak"
        if self.hint.text() != message:
            self.hint.setText(message)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if offers_file_copy(event):
            accept_copy(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self.format_at(event) and offers_file_copy(event):
            accept_copy(event)
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        source = local_drop_path(event)
        output_format = self.format_at(event)
        if source is not None and source.is_file() and output_format:
            accept_copy(event)
            self.hide()
            self.file_dropped.emit(source, output_format)
        else:
            event.ignore()

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
