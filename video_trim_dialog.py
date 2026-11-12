"""Video kesitinin başlangıç ve bitişini seçtirir ve önizletir."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from video_preview import FramePreview
from media_timeline import MediaTimeline
from video_tools import format_timestamp, parse_clip_range


class VideoTrimDialog(QDialog):
    def __init__(self, source: Path, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Videoyu kes")
        self.setMinimumWidth(360)
        self.interval: tuple[int, int] | None = None

        layout = QVBoxLayout(self)
        name = QLabel(source.name)
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        layout.addWidget(name)
        layout.addWidget(QLabel("Saniye veya dakika:saniye gir. Örneğin 12,5 ya da 00:12.500."))

        form = QFormLayout()
        self.start = QLineEdit("0")
        self.end = QLineEdit()
        self.end.setPlaceholderText("Ör. 15")
        form.addRow("&Başlangıç", self.start)
        form.addRow("B&itiş", self.end)
        layout.addLayout(form)
        self.timeline = MediaTimeline(source, self.start, self.end, video=True)
        layout.addWidget(self.timeline)
        self.finished.connect(self.timeline.player.stop)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self.preview_title = QLabel()
        layout.addWidget(self.preview_title)
        self.preview = FramePreview(source, self)
        self.preview.busy_changed.connect(self.update_controls)
        layout.addWidget(self.preview)

        preview_actions = QHBoxLayout()
        self.preview_start = QPushButton("Başlangıcı önizle")
        self.preview_start.clicked.connect(lambda: self.load_preview(0))
        preview_actions.addWidget(self.preview_start)
        self.preview_end = QPushButton("Bitişi önizle")
        self.preview_end.clicked.connect(lambda: self.load_preview(1))
        preview_actions.addWidget(self.preview_end)
        layout.addLayout(preview_actions)

        buttons = QDialogButtonBox()
        self.save = buttons.addButton("Kesiti kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel = buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
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
        self.preview_title.clear()
        self.preview.setText("Başlangıç veya bitiş zamanındaki kareyi önizleyebilirsin.")
        self.update_controls()

    def load_preview(self, endpoint: int) -> None:
        if self.interval is None or self.preview.busy:
            return
        timestamp = format_timestamp(self.interval[endpoint])
        label = "Başlangıç" if endpoint == 0 else "Bitiş"
        self.preview_title.setText(f"{label} · {timestamp.replace('.', ',')} saniye")
        self.preview.load(timestamp)

    def update_controls(self) -> None:
        busy = self.preview.busy
        ready = self.interval is not None and not busy
        self.start.setEnabled(not busy)
        self.end.setEnabled(not busy)
        self.save.setEnabled(ready)
        self.preview_start.setEnabled(ready)
        self.preview_end.setEnabled(ready)
        self.cancel.setEnabled(not busy)

    def reject(self) -> None:
        if not self.preview.busy:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.preview.busy:
            event.ignore()
        else:
            super().closeEvent(event)
