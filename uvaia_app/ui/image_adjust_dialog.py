"""Parlaklık, kontrast ve doygunluğu görsel önizlemesiyle ayarlar."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from uvaia_app.core.image_conversion import ImageAdjustments
from uvaia_app.ui.image_preview import ImagePreview, to_qimage

ADJUSTMENT_LABELS = ("Parlaklık", "Kontrast", "Doygunluk")


class ImageAdjustDialog(QDialog):
    def __init__(self, image: Image.Image, parent: QWidget) -> None:
        super().__init__(parent)
        self.original = image
        self.setWindowTitle("Görsel ayarları")
        self.resize(640, 530)

        layout = QVBoxLayout(self)
        self.preview = ImagePreview(to_qimage(image), self)
        layout.addWidget(self.preview, 1)

        form = QFormLayout()
        self.sliders: list[QSlider] = []
        self.values: list[QLabel] = []
        for label in ADJUSTMENT_LABELS:
            row = QHBoxLayout()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setAccessibleName(label)
            slider.setRange(0, 200)
            slider.setValue(100)
            slider.setPageStep(10)
            row.addWidget(slider, 1)
            value = QLabel("%100")
            value.setMinimumWidth(value.sizeHint().width())
            row.addWidget(value)
            form.addRow(label, row)
            self.sliders.append(slider)
            self.values.append(value)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        reset = buttons.addButton("Sıfırla", QDialogButtonBox.ButtonRole.ResetRole)
        reset.clicked.connect(self.reset_values)
        self.save = buttons.addButton("Kopyayı kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        self.save.setEnabled(False)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for slider in self.sliders:
            slider.valueChanged.connect(self.update_preview)

    def settings(self) -> ImageAdjustments:
        return ImageAdjustments(*(slider.value() for slider in self.sliders))

    def update_preview(self) -> None:
        settings = self.settings()
        for slider, label in zip(self.sliders, self.values, strict=True):
            label.setText(f"%{slider.value()}")
        self.preview.show_image(to_qimage(settings.apply(self.original)))
        self.save.setEnabled(settings != ImageAdjustments())

    def reset_values(self) -> None:
        for slider in self.sliders:
            with QSignalBlocker(slider):
                slider.setValue(100)
        self.update_preview()
