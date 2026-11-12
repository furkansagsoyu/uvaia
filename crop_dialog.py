"""Görsel önizlemesinde fareyle kırpma alanı seçtirir."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPaintEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from image_conversion import CropBounds

SELECTION_COLOR = QColor("#ffc447")


class CropPreview(QWidget):
    selection_changed = Signal(bool)

    def __init__(self, image: QImage, parent: QWidget) -> None:
        super().__init__(parent)
        self.image = image
        self.start: QPointF | None = None
        self.end: QPointF | None = None
        self.dragging = False
        self.setMinimumSize(320, 220)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName("Görsel kırpma önizlemesi")

    def image_rect(self) -> QRectF:
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        width = self.image.width() * scale
        height = self.image.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def normalize(self, position: QPointF) -> QPointF:
        rect = self.image_rect()
        x = (position.x() - rect.left()) / rect.width()
        y = (position.y() - rect.top()) / rect.height()
        return QPointF(min(1.0, max(0.0, x)), min(1.0, max(0.0, y)))

    def bounds(self) -> CropBounds | None:
        if self.start is None or self.end is None:
            return None
        selection = QRectF(self.start, self.end).normalized()
        if selection.isEmpty():
            return None
        return selection.left(), selection.top(), selection.right(), selection.bottom()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.image_rect().contains(event.position()):
            self.start = self.end = self.normalize(event.position())
            self.dragging = True
            self.selection_changed.emit(False)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.dragging:
            self.end = self.normalize(event.position())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.dragging:
            self.end = self.normalize(event.position())
            self.dragging = False
            self.selection_changed.emit(self.bounds() is not None)
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.image_rect()
        painter.drawImage(rect, self.image)
        bounds = self.bounds()
        if bounds is None:
            return
        left, top, right, bottom = bounds
        selection = QRectF(
            rect.left() + left * rect.width(),
            rect.top() + top * rect.height(),
            (right - left) * rect.width(),
            (bottom - top) * rect.height(),
        )
        mask = QPainterPath()
        mask.addRect(rect)
        mask.addRect(selection)
        painter.fillPath(mask, QColor(0, 0, 0, 145))
        painter.setPen(QPen(SELECTION_COLOR, 2))
        painter.drawRect(selection)


class CropDialog(QDialog):
    def __init__(self, image: QImage, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Görseli kırp")
        self.resize(660, 510)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Kırpmak istediğin alanı fareyle seç."))
        self.preview = CropPreview(image, self)
        layout.addWidget(self.preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        self.save = buttons.addButton(
            "Kırpılmış kopyayı kaydet", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.save.setEnabled(False)
        self.preview.selection_changed.connect(self.save.setEnabled)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
