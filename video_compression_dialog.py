"""MP4 sıkıştırması için çözünürlük ve kalite seçtirir."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout, QWidget,
)

from video_tools import VideoCompression


class VideoCompressionDialog(QDialog):
    def __init__(self, filename: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Videoyu sıkıştır")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        name = QLabel(filename)
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        layout.addWidget(name)

        form = QFormLayout()
        self.height = QComboBox()
        for label, height in (
            ("Kaynak boyutu", 0), ("1080p", 1080), ("720p", 720), ("480p", 480)
        ):
            self.height.addItem(label, height)
        self.height.setCurrentIndex(2)
        form.addRow("&En fazla yükseklik", self.height)

        self.quality = QComboBox()
        for label, crf in (("Yüksek kalite", 23), ("Dengeli", 28), ("Daha küçük dosya", 33)):
            self.quality.addItem(label, crf)
        self.quality.setCurrentIndex(1)
        form.addRow("&Kalite", self.quality)
        layout.addLayout(form)

        hint = QLabel("Uvaia yalnızca kaynak videodan küçük bir MP4 elde ederse kaydeder.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox()
        self.save = buttons.addButton("Sıkıştır ve kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def settings(self) -> VideoCompression:
        return VideoCompression(self.height.currentData(), self.quality.currentData())
