"""Uvaia'nın Qt masaüstü arayüzü."""

from __future__ import annotations

import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Xlib import error as x11_error

from crop_dialog import CropDialog, read_preview
from drag_wheel import (
    WHEEL_POSITIONS,
    DragWheel,
    WheelMonitor,
    accept_copy,
    local_drop_path,
    offers_file_copy,
)
from image_conversion import FORMATS, convert_image
from pdf_dialog import PdfMergeDialog
from pdf_tools import extract_pages, merge_pdfs
from video_audio import VIDEO_EXTENSIONS, extract_mp3

STYLE = """
QWidget { background: #172321; color: #eff6ed; font-size: 15px; }
QLabel#title { font-size: 34px; font-weight: 700; }
QLabel#status { color: #c4d6c7; }
QLabel#dropZone {
    border: 2px dashed #789688; border-radius: 20px; padding: 30px;
    background: #20312c;
}
QPushButton { background: #2b433a; border: 2px solid transparent;
    border-radius: 12px; padding: 10px 16px; }
QPushButton[format="true"] { background: #eac174; color: #172321;
    border-radius: 26px; font-weight: 700; min-height: 28px; }
QPushButton:focus { border-color: #ffffff; }
QPushButton:hover { border-color: #a1cbb4; }
QPushButton:disabled { color: #9ba9a2; background: #283430; }
"""


class FileJob(QThread):
    """Dosya işlemini pencereyi dondurmadan yürütür."""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, operation: Callable[[], Path], parent: QWidget) -> None:
        super().__init__(parent)
        self.operation = operation

    def run(self) -> None:
        try:
            output = self.operation()
        except Image.DecompressionBombError:
            self.failed.emit("Görsel güvenli işlem boyutunu aşıyor.")
        except (OSError, ValueError) as error:
            self.failed.emit(str(error))
        else:
            self.succeeded.emit(output.name)


class Window(QWidget):
    """Görsel seçimi, işlem çarkı ve çıktı durumu."""

    def __init__(self) -> None:
        super().__init__()
        self.source: Path | None = None
        self.job: FileJob | None = None
        self.monitor: WheelMonitor | None = None
        self.setWindowTitle("Uvaia")
        self.setAcceptDrops(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("Uvaia")
        title.setObjectName("title")
        layout.addWidget(title)

        self.drop_zone = QLabel("Bir görsel, PDF veya video bırak")
        self.drop_zone.setObjectName("dropZone")
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.setWordWrap(True)
        layout.addWidget(self.drop_zone)

        self.pick = QPushButton("Görsel seç…")
        self.pick.clicked.connect(self.choose_image)
        layout.addWidget(self.pick)

        self.wheel = QWidget()
        wheel_layout = QGridLayout(self.wheel)
        wheel_layout.setSpacing(8)
        center = QLabel("Dönüştür")
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wheel_layout.addWidget(center, 1, 1)
        for output_format, position in zip(FORMATS, WHEEL_POSITIONS, strict=True):
            button = QPushButton(output_format)
            button.setProperty("format", True)
            button.clicked.connect(lambda checked=False, fmt=output_format: self.convert(fmt))
            wheel_layout.addWidget(button, *position)
        resize_button = QPushButton("Görseli küçült…")
        resize_button.clicked.connect(self.choose_scale)
        wheel_layout.addWidget(resize_button, 3, 0, 1, 3)
        crop_button = QPushButton("Görseli kırp…")
        crop_button.clicked.connect(self.choose_crop)
        wheel_layout.addWidget(crop_button, 4, 0, 1, 3)
        self.wheel.hide()
        layout.addWidget(self.wheel)

        self.pdf_button = QPushButton("PDF birleştir…")
        self.pdf_button.clicked.connect(self.choose_pdfs)
        layout.addWidget(self.pdf_button)

        self.pages_button = QPushButton("PDF’den sayfa çıkar…")
        self.pages_button.clicked.connect(self.choose_pages)
        layout.addWidget(self.pages_button)

        self.audio_button = QPushButton("Videodan MP3 çıkar…")
        self.audio_button.clicked.connect(self.choose_video)
        layout.addWidget(self.audio_button)

        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def start_drag_monitor(self) -> None:
        if QApplication.platformName() != "xcb":
            return
        wheel = DragWheel(STYLE)
        try:
            self.monitor = WheelMonitor(self, wheel)
        except x11_error.DisplayError:
            return
        wheel.file_dropped.connect(self.convert_drop)
        QApplication.instance().aboutToQuit.connect(self.monitor.shutdown)
        self.drop_zone.setText("Görsel, PDF veya video bırak. Görsel çarkı için Shift’e bas.")

    def convert_drop(self, source: Path, output_format: str) -> None:
        self.select_image(source)
        self.showNormal()
        self.raise_()
        self.convert(output_format)

    def choose_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Görsel seç")
        if filename:
            self.select_file(Path(filename))

    def select_file(self, source: Path) -> None:
        extension = source.suffix.lower()
        if extension in VIDEO_EXTENSIONS:
            self.select_video(source)
        elif extension == ".pdf":
            self.select_pdf(source)
        else:
            self.select_image(source)

    def select_image(self, source: Path) -> None:
        self.source = source
        self.drop_zone.setText(source.name)
        self.wheel.show()
        self.audio_button.setText("Videodan MP3 çıkar…")
        self.status.clear()

    def select_video(self, source: Path) -> None:
        self.source = source
        self.drop_zone.setText(source.name)
        self.wheel.hide()
        self.audio_button.setText("MP3 olarak kaydet")
        self.status.clear()

    def select_pdf(self, source: Path) -> None:
        self.source = source
        self.drop_zone.setText(source.name)
        self.wheel.hide()
        self.audio_button.setText("Videodan MP3 çıkar…")
        self.status.clear()

    def choose_video(self) -> None:
        if self.job is not None:
            return
        source = self.source
        if source is None or source.suffix.lower() not in VIDEO_EXTENSIONS:
            extensions = " ".join(f"*{ext} *{ext.upper()}" for ext in VIDEO_EXTENSIONS)
            self.set_drag_monitor_enabled(False)
            try:
                filename, _ = QFileDialog.getOpenFileName(
                    self, "Sesini çıkaracağın videoyu seç", filter=f"Video ({extensions})"
                )
            finally:
                self.set_drag_monitor_enabled(True)
            if not filename:
                return
            source = Path(filename)
            self.select_video(source)
        self.start_job(partial(extract_mp3, source), "MP3 hazırlanıyor…")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.job is None and offers_file_copy(event):
            accept_copy(event)

    def dropEvent(self, event: QDropEvent) -> None:
        source = local_drop_path(event)
        if self.job is None and source is not None and source.is_file():
            self.select_file(source)
            accept_copy(event)

    def set_drag_monitor_enabled(self, enabled: bool) -> None:
        if self.monitor is not None:
            self.monitor.enabled = enabled
            if not enabled:
                self.monitor.wheel.hide()

    def choose_scale(self) -> None:
        if self.source is None or self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            percent, accepted = QInputDialog.getInt(
                self, "Görseli küçült", "Yeni boyut (%)", 50, 1, 99, 1
            )
        finally:
            self.set_drag_monitor_enabled(True)
        if accepted:
            self.convert(None, scale_percent=percent)

    def choose_crop(self) -> None:
        source = self.source
        if source is None or self.job is not None:
            return
        try:
            preview = read_preview(source)
        except Image.DecompressionBombError:
            self.status.setText("Görsel güvenli işlem boyutunu aşıyor.")
            return
        except (OSError, ValueError) as error:
            self.status.setText(f"Önizleme açılamadı: {error}")
            return

        self.set_drag_monitor_enabled(False)
        dialog = CropDialog(preview, self)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                bounds = dialog.preview.bounds()
                if bounds is not None:
                    operation = partial(convert_image, source, None, crop_bounds=bounds)
                    self.start_job(operation, "Görsel kırpılıyor…")
        finally:
            dialog.deleteLater()
            self.set_drag_monitor_enabled(self.job is None)

    def choose_pdfs(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        dialog = PdfMergeDialog(self)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.start_job(partial(merge_pdfs, dialog.paths()), "PDF’ler birleştiriliyor…")
        finally:
            dialog.deleteLater()
            self.set_drag_monitor_enabled(self.job is None)

    def choose_pages(self) -> None:
        if self.job is not None:
            return
        source = self.source
        self.set_drag_monitor_enabled(False)
        try:
            if source is None or source.suffix.lower() != ".pdf":
                filename, _ = QFileDialog.getOpenFileName(
                    self, "PDF seç", filter="PDF (*.pdf *.PDF)"
                )
                if not filename:
                    return
                source = Path(filename)
                self.select_pdf(source)

            selection, accepted = QInputDialog.getText(
                self,
                "PDF’den sayfa çıkar",
                f"{source.name}\nSayfa numaraları veya aralıkları (ör. 1, 3-5)",
            )
            if accepted:
                self.start_job(partial(extract_pages, source, selection), "Sayfalar çıkarılıyor…")
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def convert(self, output_format: str | None, *, scale_percent: int | None = None) -> None:
        if self.source is None or self.job is not None:
            return
        action = "Küçültülüyor…" if scale_percent is not None else "Dönüştürülüyor…"
        operation = partial(
            convert_image, self.source, output_format, scale_percent=scale_percent
        )
        self.start_job(operation, action)

    def start_job(self, operation: Callable[[], Path], status: str) -> None:
        self.set_drag_monitor_enabled(False)
        self.status.setText(status)
        self.set_file_controls_enabled(False)
        self.job = FileJob(operation, self)
        self.job.succeeded.connect(lambda name: self.status.setText(f"Kaydedildi: {name}"))
        self.job.failed.connect(lambda message: self.status.setText(f"İşlem tamamlanamadı: {message}"))
        self.job.finished.connect(self.job_finished)
        self.job.finished.connect(self.job.deleteLater)
        self.job.start()

    def job_finished(self) -> None:
        self.job = None
        self.set_drag_monitor_enabled(True)
        self.set_file_controls_enabled(True)

    def set_file_controls_enabled(self, enabled: bool) -> None:
        self.pick.setEnabled(enabled)
        self.wheel.setEnabled(enabled)
        self.pdf_button.setEnabled(enabled)
        self.pages_button.setEnabled(enabled)
        self.audio_button.setEnabled(enabled)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.job is not None:
            event.ignore()
        else:
            super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Uvaia")
    window = Window()
    window.start_drag_monitor()
    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).expanduser().absolute()
        if path.is_file():
            window.select_file(path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
