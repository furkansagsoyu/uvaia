"""Uvaia'nın Qt masaüstü arayüzü."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Xlib import error as x11_error

from compression_dialog import CompressionDialog
from crop_dialog import CropDialog, read_preview
from drag_wheel import (
    WHEEL_POSITIONS,
    DragWheel,
    WheelMonitor,
    accept_copy,
    local_drop_paths,
    offers_file_copy,
)
from image_conversion import FORMATS, compress_image, convert_image, convert_images
from file_order_dialog import FileOrderDialog
from pdf_tools import extract_pages, images_to_pdf, merge_pdfs
from qr_reader import read_qr_codes
from video_tools import VIDEO_EXTENSIONS, extract_frame, extract_mp3, trim_video
from video_trim_dialog import VideoTrimDialog

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

    def __init__(self, operation: Callable[[], Path | str], parent: QWidget) -> None:
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
            message = f"Kaydedildi: {output.name}" if isinstance(output, Path) else output
            self.succeeded.emit(message)


class Window(QWidget):
    """Görsel seçimi, işlem çarkı ve çıktı durumu."""

    def __init__(self) -> None:
        super().__init__()
        self.source: Path | None = None
        self.batch_sources: tuple[Path, ...] = ()
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

        self.drop_zone = QLabel("Görselleri, PDF’yi veya videoyu bırak")
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
        self.resize_button = QPushButton("Görseli küçült…")
        self.resize_button.clicked.connect(self.choose_scale)
        wheel_layout.addWidget(self.resize_button, 3, 0, 1, 3)
        self.crop_button = QPushButton("Görseli kırp…")
        self.crop_button.clicked.connect(self.choose_crop)
        wheel_layout.addWidget(self.crop_button, 4, 0, 1, 3)
        self.compress_button = QPushButton("Görseli sıkıştır…")
        self.compress_button.clicked.connect(self.choose_compression)
        wheel_layout.addWidget(self.compress_button, 5, 0, 1, 3)
        self.wheel.hide()
        layout.addWidget(self.wheel)

        self.pdf_button = QPushButton("PDF birleştir…")
        self.pdf_button.clicked.connect(lambda: self.choose_pdfs())
        layout.addWidget(self.pdf_button)

        self.pages_button = QPushButton("PDF’den sayfa çıkar…")
        self.pages_button.clicked.connect(self.choose_pages)
        layout.addWidget(self.pages_button)

        self.images_pdf_button = QPushButton("Görsellerden PDF…")
        self.images_pdf_button.clicked.connect(self.choose_images_for_pdf)
        layout.addWidget(self.images_pdf_button)

        self.audio_button = QPushButton("Videodan MP3 çıkar…")
        self.audio_button.clicked.connect(self.choose_video)
        layout.addWidget(self.audio_button)

        self.frame_button = QPushButton("Videodan kare al…")
        self.frame_button.clicked.connect(self.choose_frame)
        layout.addWidget(self.frame_button)

        self.trim_button = QPushButton("Videoyu kes…")
        self.trim_button.clicked.connect(self.choose_trim)
        layout.addWidget(self.trim_button)

        self.qr_button = QPushButton("QR kodu oku…")
        self.qr_button.clicked.connect(self.choose_qr)
        layout.addWidget(self.qr_button)

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
        self.drop_zone.setText("Görselleri, PDF’yi veya videoyu bırak. Görsel çarkı için Shift’e bas.")

    def convert_drop(self, paths: tuple[Path, ...], output_format: str) -> None:
        if self.job is not None:
            return
        self.showNormal()
        self.raise_()
        if len(paths) == 1:
            self.select_file(paths[0])
            if self.wheel.isHidden():
                self.status.setText("Format çarkı görselleri dönüştürür.")
                return
        elif not self.select_batch(paths):
            return
        self.convert(output_format)

    def choose_image(self) -> None:
        self.set_drag_monitor_enabled(False)
        try:
            filenames, _ = QFileDialog.getOpenFileNames(self, "Görselleri seç")
        finally:
            self.set_drag_monitor_enabled(True)
        paths = tuple(dict.fromkeys(Path(filename) for filename in filenames))
        if len(paths) == 1:
            self.select_file(paths[0])
        elif paths:
            self.select_batch(paths)

    def select_batch(self, paths: tuple[Path, ...]) -> bool:
        if any(path.suffix.lower() in (*VIDEO_EXTENSIONS, ".pdf") for path in paths):
            self.status.setText("Toplu dönüştürme için yalnızca görselleri seç.")
            return False
        self.source = None
        self.batch_sources = paths
        self.drop_zone.setText(f"{len(paths)} görsel seçildi")
        self.wheel.show()
        self.resize_button.hide()
        self.crop_button.hide()
        self.compress_button.hide()
        self.audio_button.setText("Videodan MP3 çıkar…")
        self.status.clear()
        return True

    def select_file(self, source: Path) -> None:
        extension = source.suffix.lower()
        if extension in VIDEO_EXTENSIONS:
            self.select_video(source)
        elif extension == ".pdf":
            self.select_pdf(source)
        else:
            self.select_image(source)

    def select_image(self, source: Path) -> None:
        self.batch_sources = ()
        self.source = source
        self.resize_button.show()
        self.crop_button.show()
        self.compress_button.show()
        self.drop_zone.setText(source.name)
        self.wheel.show()
        self.audio_button.setText("Videodan MP3 çıkar…")
        self.status.clear()

    def select_video(self, source: Path) -> None:
        self.batch_sources = ()
        self.source = source
        self.drop_zone.setText(source.name)
        self.wheel.hide()
        self.audio_button.setText("MP3 olarak kaydet")
        self.status.clear()

    def select_pdf(self, source: Path) -> None:
        self.batch_sources = ()
        self.source = source
        self.drop_zone.setText(source.name)
        self.wheel.hide()
        self.audio_button.setText("Videodan MP3 çıkar…")
        self.status.clear()

    def choose_video_source(self, title: str) -> Path | None:
        source = self.source
        if source is not None and source.suffix.lower() in VIDEO_EXTENSIONS:
            return source

        extensions = " ".join(f"*{ext} *{ext.upper()}" for ext in VIDEO_EXTENSIONS)
        filename, _ = QFileDialog.getOpenFileName(self, title, filter=f"Video ({extensions})")
        if not filename:
            return None

        source = Path(filename)
        self.select_video(source)
        return source

    def choose_video(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_video_source("Sesini çıkaracağın videoyu seç")
            if source is not None:
                self.start_job(partial(extract_mp3, source), "MP3 hazırlanıyor…")
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_frame(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_video_source("Kare alacağın videoyu seç")
            if source is None:
                return
            timestamp, accepted = QInputDialog.getText(
                self,
                "Videodan kare al",
                f"{source.name}\nKare zamanı (ör. 12,5 saniye için 12,5 veya 00:12.500)",
                text="0",
            )
            if accepted:
                self.start_job(partial(extract_frame, source, timestamp), "Video karesi hazırlanıyor…")
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_trim(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_video_source("Kesilecek videoyu seç")
            if source is None:
                return
            dialog = VideoTrimDialog(source.name, self)
            try:
                if dialog.exec() == QDialog.DialogCode.Accepted and dialog.interval:
                    operation = partial(trim_video, source, *dialog.interval)
                    self.start_job(operation, "Video kesiti hazırlanıyor…")
            finally:
                dialog.deleteLater()
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.job is None and offers_file_copy(event):
            accept_copy(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if self.job is not None:
            return
        paths = local_drop_paths(event)
        if len(paths) == 1:
            self.select_file(paths[0])
            accept_copy(event)
        elif paths and self.select_batch(paths):
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

    def choose_compression(self) -> None:
        source = self.source
        if source is None or self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        dialog = CompressionDialog(source.name, self)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                operation = partial(
                    compress_image, source, dialog.output_format.currentText(), dialog.quality.value()
                )
                self.start_job(operation, "Görsel sıkıştırılıyor…")
        finally:
            dialog.deleteLater()
            self.set_drag_monitor_enabled(self.job is None)

    def choose_qr(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.source
            if source is None or self.wheel.isHidden():
                filename, _ = QFileDialog.getOpenFileName(self, "QR kodu içeren görseli seç")
                if not filename:
                    return
                source = Path(filename)
                self.select_image(source)
            self.start_job(
                partial(read_qr_codes, source),
                "QR kodu aranıyor…",
                on_success=self.show_qr_result,
            )
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    @Slot(str)
    def show_qr_result(self, payload: str) -> None:
        self.status.setText("QR kodu okundu.")
        self.set_drag_monitor_enabled(False)
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle("QR kodu içeriği")
        dialog.resize(460, 270)
        layout = QVBoxLayout(dialog)
        content = QPlainTextEdit()
        content.setAccessibleName("QR kodu içeriği")
        content.setPlainText(payload)
        content.setReadOnly(True)
        layout.addWidget(content)

        buttons = QDialogButtonBox()
        copy = buttons.addButton("Panoya kopyala", QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton("Kapat", QDialogButtonBox.ButtonRole.RejectRole)

        def copy_payload() -> None:
            selection = content.textCursor().selectedText()
            text = selection.replace("\u2029", "\n") if selection else payload
            QApplication.clipboard().setText(text)
            copy.setText("Kopyalandı")

        copy.clicked.connect(copy_payload)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.finished.connect(lambda: self.set_drag_monitor_enabled(self.job is None))
        dialog.open()

    def choose_pdfs(self, initial: tuple[Path, ...] = ()) -> None:
        if self.job is not None:
            return
        dialog = FileOrderDialog(
            self,
            title="PDF birleştir",
            hint="PDF’ler yukarıdan aşağıya birleştirilir.",
            add_label="PDF ekle…",
            save_label="Birleştir",
            file_filter="PDF (*.pdf *.PDF)",
            minimum=2,
            initial=initial,
        )
        self.run_file_order_dialog(dialog, merge_pdfs, "PDF’ler birleştiriliyor…")

    def choose_images_for_pdf(self) -> None:
        if self.job is not None:
            return
        initial = self.batch_sources
        if self.source is not None and not self.wheel.isHidden():
            initial = (self.source,)
        dialog = FileOrderDialog(
            self,
            title="Görsellerden PDF oluştur",
            hint="Her görsel listedeki sırayla bir sayfaya yerleştirilir.",
            add_label="Görsel ekle…",
            save_label="PDF oluştur",
            file_filter="Tüm dosyalar (*)",
            minimum=1,
            initial=initial,
        )
        self.run_file_order_dialog(dialog, images_to_pdf, "PDF hazırlanıyor…")

    def run_file_order_dialog(
        self,
        dialog: FileOrderDialog,
        operation: Callable[[list[Path]], Path],
        status: str,
    ) -> None:
        self.set_drag_monitor_enabled(False)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.start_job(partial(operation, dialog.paths()), status)
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
        if self.job is not None:
            return
        if self.batch_sources and output_format is not None:
            operation = partial(convert_images, self.batch_sources, output_format)
            self.start_job(operation, "Görseller dönüştürülüyor…")
            return
        if self.source is None:
            return
        action = "Küçültülüyor…" if scale_percent is not None else "Dönüştürülüyor…"
        operation = partial(
            convert_image, self.source, output_format, scale_percent=scale_percent
        )
        self.start_job(operation, action)

    def start_job(
        self,
        operation: Callable[[], Path | str],
        status: str,
        *,
        on_success: Callable[[str], None] | None = None,
    ) -> None:
        self.set_drag_monitor_enabled(False)
        self.status.setText(status)
        self.set_file_controls_enabled(False)
        self.job = FileJob(operation, self)
        self.job.succeeded.connect(on_success or self.status.setText)
        self.job.failed.connect(lambda message: self.status.setText(f"İşlem tamamlanamadı: {message}"))
        self.job.finished.connect(self.job_finished)
        self.job.finished.connect(self.job.deleteLater)
        self.job.start()

    def job_finished(self) -> None:
        self.job = None
        self.set_drag_monitor_enabled(QApplication.activeModalWidget() is None)
        self.set_file_controls_enabled(True)

    def set_file_controls_enabled(self, enabled: bool) -> None:
        self.pick.setEnabled(enabled)
        self.wheel.setEnabled(enabled)
        self.pdf_button.setEnabled(enabled)
        self.pages_button.setEnabled(enabled)
        self.images_pdf_button.setEnabled(enabled)
        self.audio_button.setEnabled(enabled)
        self.frame_button.setEnabled(enabled)
        self.trim_button.setEnabled(enabled)
        self.qr_button.setEnabled(enabled)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.job is not None:
            event.ignore()
        else:
            super().closeEvent(event)


def open_startup_files(window: Window, paths: tuple[Path, ...]) -> None:
    for path in paths:
        if not path.is_file():
            window.status.setText(f"Dosya bulunamadı: {path.name}")
            return
    if len(paths) == 1:
        window.select_file(paths[0])
    elif paths and all(path.suffix.lower() == ".pdf" for path in paths):
        QTimer.singleShot(0, lambda: window.choose_pdfs(paths))
    elif paths:
        window.select_batch(paths)


def main() -> int:
    parser = argparse.ArgumentParser(description="Yerel görsel, PDF ve video araçları.")
    parser.add_argument("files", nargs="*", metavar="dosya")
    args = parser.parse_args()
    paths = tuple(dict.fromkeys(Path(name).expanduser().absolute() for name in args.files))

    app = QApplication([sys.argv[0]])
    app.setApplicationName("Uvaia")
    window = Window()
    window.start_drag_monitor()
    window.show()
    open_startup_files(window, paths)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
