"""Kaydetmeden önce seçilen zamandaki video karesini gösterir."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QPixmap
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

from video_tools import preview_frame, timestamp_milliseconds


class FramePreviewJob(QThread):
    ready = Signal(bytes)
    failed = Signal(str)

    def __init__(self, source: Path, timestamp: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.source = source
        self.timestamp = timestamp

    def run(self) -> None:
        try:
            self.ready.emit(preview_frame(self.source, self.timestamp))
        except (OSError, ValueError) as error:
            self.failed.emit(str(error))


class VideoFrameDialog(QDialog):
    def __init__(self, source: Path, parent: QWidget) -> None:
        super().__init__(parent)
        self.source = source
        self.job: FramePreviewJob | None = None
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

        self.preview = QLabel()
        self.preview.setMinimumSize(320, 180)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setWordWrap(True)
        self.preview.setAccessibleName("Video karesi önizlemesi")
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
        if self.job is not None or not self.preview_button.isEnabled():
            return
        self.preview.setText("Önizleme hazırlanıyor…")
        self.preview_button.setEnabled(False)
        self.timestamp.setEnabled(False)
        self.save.setEnabled(False)
        self.cancel.setEnabled(False)
        self.job = FramePreviewJob(self.source, self.timestamp.text(), self)
        self.job.ready.connect(self.show_preview)
        self.job.failed.connect(self.preview.setText)
        self.job.finished.connect(self.preview_finished)
        self.job.finished.connect(self.job.deleteLater)
        self.job.start()

    @Slot(bytes)
    def show_preview(self, data: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data, "PNG"):
            self.preview.setPixmap(pixmap)
        else:
            self.preview.setText("Önizleme görüntüsü açılamadı.")

    @Slot()
    def preview_finished(self) -> None:
        self.job = None
        self.timestamp.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.save.setEnabled(True)
        self.cancel.setEnabled(True)

    def reject(self) -> None:
        if self.job is None:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.job is not None:
            event.ignore()
        else:
            super().closeEvent(event)
