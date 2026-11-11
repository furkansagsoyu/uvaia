"""Video araçlarının ortak, arka planda yüklenen kare önizlemesi."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from video_tools import preview_frame


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


class FramePreview(QLabel):
    busy_changed = Signal(bool)

    def __init__(self, source: Path, parent: QWidget) -> None:
        super().__init__(parent)
        self.source = source
        self.job: FramePreviewJob | None = None
        self.setMinimumSize(320, 180)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setAccessibleName("Video karesi önizlemesi")

    @property
    def busy(self) -> bool:
        return self.job is not None

    def load(self, timestamp: str) -> None:
        if self.busy:
            return
        self.setText("Önizleme hazırlanıyor…")
        self.job = FramePreviewJob(self.source, timestamp, self)
        self.job.ready.connect(self.show_frame)
        self.job.failed.connect(self.setText)
        self.job.finished.connect(self.finish)
        self.job.finished.connect(self.job.deleteLater)
        self.busy_changed.emit(True)
        self.job.start()

    @Slot(bytes)
    def show_frame(self, data: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data, "PNG"):
            self.setPixmap(pixmap)
        else:
            self.setText("Önizleme görüntüsü açılamadı.")

    @Slot()
    def finish(self) -> None:
        self.job = None
        self.busy_changed.emit(False)
