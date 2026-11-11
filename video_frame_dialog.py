"""Kaydetmeden önce seçilen zamandaki video karesini gösterir."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from video_preview import FramePreview
from video_tools import timestamp_milliseconds


class VideoFrameDialog(QDialog):
    def __init__(self, source: Path, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Videodan kare al")
        self.setMinimumWidth(370)

        layout = QVBoxLayout(self)
        name = QLabel(source.name)
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        layout.addWidget(name)

        form = QFormLayout()
        self.timestamp = QLineEdit("0")
        self.timestamp.setPlaceholderText("Ör. 12,5 veya 00:12.500")
        form.addRow("&Kare zamanı", self.timestamp)
        layout.addLayout(form)

        self.preview = FramePreview(source, self)
        self.preview.busy_changed.connect(self.set_preview_busy)
        layout.addWidget(self.preview)

        self.preview_button = QPushButton("Önizle")
        self.preview_button.clicked.connect(self.load_preview)
        layout.addWidget(self.preview_button)

        buttons = QDialogButtonBox()
        self.save = buttons.addButton("PNG olarak kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel = buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.timestamp.textChanged.connect(self.update_timestamp)
        self.update_timestamp()

    def update_timestamp(self) -> None:
        try:
            timestamp_milliseconds(self.timestamp.text())
        except ValueError as error:
            self.preview.setText(str(error))
            valid = False
        else:
            self.preview.setText("Seçtiğin kareyi görmek için Önizle’ye bas.")
            valid = True
        self.save.setEnabled(valid)
        self.preview_button.setEnabled(valid)

    def load_preview(self) -> None:
        if self.preview_button.isEnabled():
            self.preview.load(self.timestamp.text())

    def set_preview_busy(self, busy: bool) -> None:
        self.preview_button.setEnabled(not busy)
        self.timestamp.setEnabled(not busy)
        self.save.setEnabled(not busy)
        self.cancel.setEnabled(not busy)

    def reject(self) -> None:
        if not self.preview.busy:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.preview.busy:
            event.ignore()
        else:
            super().closeEvent(event)
