"""Görsel döndürme ve yansıtma işlemlerini önizletir."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QResizeEvent, QTransform
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from image_conversion import Orientation


class OrientationPreview(QLabel):
    def __init__(self, image: QImage, parent: QWidget) -> None:
        super().__init__(parent)
        self.image = image
        self.setMinimumSize(320, 220)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName("Görsel önizlemesi")

    def show_image(self, image: QImage) -> None:
        self.image = image
        self.refresh()

    def refresh(self) -> None:
        image = self.image.scaled(
            self.contentsRect().size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(QPixmap.fromImage(image))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.refresh()


class OrientationDialog(QDialog):
    def __init__(self, image: QImage, parent: QWidget) -> None:
        super().__init__(parent)
        self.image = image
        self.orientation = Orientation()
        self.setWindowTitle("Döndür ve yansıt")
        self.resize(640, 450)

        layout = QVBoxLayout(self)
        self.preview = OrientationPreview(image, self)
        layout.addWidget(self.preview, 1)
        actions = QHBoxLayout()
        for label, change in (
            ("Sola döndür", lambda: self.orientation.rotate(-1)),
            ("Sağa döndür", lambda: self.orientation.rotate(1)),
            ("Yatay yansıt", lambda: self.orientation.flip_horizontal()),
            ("Dikey yansıt", lambda: self.orientation.flip_vertical()),
            ("Sıfırla", Orientation),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, action=change: self.apply(action))
            actions.addWidget(button)
        layout.addLayout(actions)

        buttons = QDialogButtonBox()
        self.save = buttons.addButton("Kopyayı kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        self.save.setEnabled(False)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self, change: Callable[[], Orientation]) -> None:
        self.orientation = change()
        image = self.image.transformed(QTransform().rotate(90 * self.orientation.turns))
        if self.orientation.mirrored:
            image = image.transformed(QTransform().scale(-1, 1))
        self.preview.show_image(image)
        self.save.setEnabled(self.orientation != Orientation())
