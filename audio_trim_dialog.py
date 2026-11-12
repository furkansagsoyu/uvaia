"""Ses kesitinin zaman aralığını ve çıktı biçimini seçtirir."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from audio_tools import AUDIO_EXPORT_OPTIONS
from media_timeline import MediaTimeline
from video_tools import format_timestamp, parse_clip_range


class AudioTrimDialog(QDialog):
    def __init__(self, source: Path, default_format: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sesi kes")
        self.setMinimumWidth(360)
        self.interval: tuple[int, int] | None = None

        layout = QVBoxLayout(self)
        name = QLabel(source.name)
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        layout.addWidget(name)

        form = QFormLayout()
        self.start = QLineEdit("0")
        self.end = QLineEdit()
        self.end.setPlaceholderText("Ör. 12,5 veya 00:12.500")
        form.addRow("&Başlangıç", self.start)
        form.addRow("B&itiş", self.end)
        self.output_format = QComboBox()
        self.output_format.addItems(list(AUDIO_EXPORT_OPTIONS))
        self.output_format.setCurrentText(default_format)
        form.addRow("&Çıktı biçimi", self.output_format)
        layout.addLayout(form)
        self.timeline = MediaTimeline(source, self.start, self.end, video=False)
        layout.addWidget(self.timeline)
        self.finished.connect(self.timeline.player.stop)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        buttons = QDialogButtonBox()
        self.save = buttons.addButton("Kesiti kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.start.textChanged.connect(self.update_interval)
        self.end.textChanged.connect(self.update_interval)
        self.end.setFocus()
        self.update_interval()

    def update_interval(self) -> None:
        self.interval = None
        if not self.start.text().strip() or not self.end.text().strip():
            self.hint.setText("Başlangıç ve bitiş zamanını gir.")
        else:
            try:
                self.interval = parse_clip_range(self.start.text(), self.end.text())
            except ValueError as error:
                self.hint.setText(str(error))
            else:
                start, end = self.interval
                duration = format_timestamp(end - start).replace(".", ",")
                self.hint.setText(f"Kesit süresi: {duration} saniye")
        self.save.setEnabled(self.interval is not None)
