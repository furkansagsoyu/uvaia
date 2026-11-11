"""Görsel düzenleyicileri için boyutu sınırlandırılmış önizleme."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

PREVIEW_LIMIT = 900


def read_preview_image(source: Path) -> Image.Image:
    with Image.open(source) as original:
        if getattr(original, "is_animated", False):
            raise ValueError("Hareketli görseller henüz desteklenmiyor.")
        original.thumbnail((PREVIEW_LIMIT, PREVIEW_LIMIT), Image.Resampling.LANCZOS)
        return ImageOps.exif_transpose(original).convert("RGBA")


def to_qimage(image: Image.Image) -> QImage:
    pixels = image.tobytes()
    return QImage(
        pixels, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888
    ).copy()


class ImagePreview(QLabel):
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
