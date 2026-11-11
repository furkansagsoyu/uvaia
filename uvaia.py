"""Uvaia'nın Qt masaüstü arayüzü."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from Xlib import error as x11_error

from compression_dialog import CompressionDialog
from crop_dialog import CropDialog
from drag_wheel import (
    WHEEL_POSITIONS,
    DragWheel,
    WheelMonitor,
    accept_copy,
    local_drop_paths,
    offers_file_copy,
)
from file_order_dialog import FileOrderDialog
from image_adjust_dialog import ImageAdjustDialog
from image_conversion import FORMATS, adjust_image, compress_image, convert_image, convert_images
from image_preview import read_preview_image, to_qimage
from ocr_tools import ocr_image, ocr_pdf
from orientation_dialog import OrientationDialog
from output_files import SavedOutputs
from pdf_render import render_pdf_pages
from pdf_render_dialog import PdfRenderDialog
from pdf_rotate_dialog import PdfRotateDialog
from pdf_text import extract_pdf_text
from pdf_tools import extract_pages, images_to_pdf, merge_pdfs, rotate_pages
from qr_reader import read_pdf_qr_codes, read_qr_codes
from video_frame_dialog import VideoFrameDialog
from video_tools import (
    VIDEO_EXPORT_OPTIONS,
    VIDEO_EXTENSIONS,
    convert_video,
    extract_frame,
    extract_mp3,
    mute_video,
    trim_video,
)
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
QTabWidget::pane { border: 1px solid #3b534a; border-radius: 10px; top: -1px; }
QTabBar::tab { padding: 10px 18px; border: 1px solid transparent;
    border-bottom: 2px solid transparent; border-top-left-radius: 8px;
    border-top-right-radius: 8px; color: #c4d6c7; }
QTabBar::tab:selected { background: #2b433a; color: #eff6ed;
    border-bottom-color: #eac174; }
QTabBar::tab:hover { background: #20312c; }
QTabBar::tab:focus { border-top-color: #a1cbb4; }
"""


FileResult = Path | SavedOutputs | str


class FileJob(QThread):
    """Dosya işlemini pencereyi dondurmadan yürütür."""

    succeeded = Signal(str)
    outputs_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, operation: Callable[[], FileResult], parent: QWidget) -> None:
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
            if isinstance(output, Path):
                self.outputs_ready.emit((output,))
                self.succeeded.emit(f"Kaydedildi: {output.name}")
            elif isinstance(output, SavedOutputs):
                self.outputs_ready.emit(output.paths)
                self.succeeded.emit(output.message)
            else:
                self.succeeded.emit(output)


class Window(QWidget):
    """Dosya seçimi, türe göre araçlar ve çıktı durumu."""

    def __init__(self) -> None:
        super().__init__()
        self.source: Path | None = None
        self.batch_sources: tuple[Path, ...] = ()
        self.output_paths: tuple[Path, ...] = ()
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

        self.tools = QTabWidget()
        self.tools.setAccessibleName("Dosya araçları")
        layout.addWidget(self.tools)
        self.image_tab = QWidget()
        self.pdf_tab = QWidget()
        self.video_tab = QWidget()
        self.tools.addTab(self.image_tab, "Görsel")
        self.tools.addTab(self.pdf_tab, "PDF")
        self.tools.addTab(self.video_tab, "Video")
        self.build_image_tools()
        self.build_pdf_tools()
        self.build_video_tools()

        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.output_actions = QWidget()
        output_layout = QHBoxLayout(self.output_actions)
        output_layout.setContentsMargins(0, 0, 0, 0)
        self.open_output_button = QPushButton("Çıktıyı aç")
        self.open_output_button.clicked.connect(self.open_output)
        output_layout.addWidget(self.open_output_button)
        self.open_folder_button = QPushButton("Çıktı klasörünü aç")
        self.open_folder_button.clicked.connect(self.open_output_folder)
        output_layout.addWidget(self.open_folder_button)
        self.output_actions.hide()
        layout.addWidget(self.output_actions)

    def build_image_tools(self) -> None:
        layout = QVBoxLayout(self.image_tab)
        self.pick = QPushButton("Görsel seç…")
        self.pick.clicked.connect(self.choose_image)
        layout.addWidget(self.pick)

        self.wheel = QWidget()
        wheel_layout = QVBoxLayout(self.wheel)
        wheel_layout.setContentsMargins(0, 0, 0, 0)
        formats = QGridLayout()
        center = QLabel("Dönüştür")
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        formats.addWidget(center, 1, 1)
        for output_format, position in zip(FORMATS, WHEEL_POSITIONS, strict=True):
            button = QPushButton(output_format)
            button.setProperty("format", True)
            button.clicked.connect(lambda checked=False, fmt=output_format: self.convert(fmt))
            formats.addWidget(button, *position)
        wheel_layout.addLayout(formats)

        editing = QGridLayout()
        self.resize_button = QPushButton("Görseli küçült…")
        self.resize_button.clicked.connect(self.choose_scale)
        editing.addWidget(self.resize_button, 0, 0)
        self.crop_button = QPushButton("Görseli kırp…")
        self.crop_button.clicked.connect(self.choose_crop)
        editing.addWidget(self.crop_button, 0, 1)
        self.compress_button = QPushButton("Görseli sıkıştır…")
        self.compress_button.clicked.connect(self.choose_compression)
        editing.addWidget(self.compress_button, 1, 0)
        self.orientation_button = QPushButton("Döndür ve yansıt…")
        self.orientation_button.clicked.connect(self.choose_orientation)
        editing.addWidget(self.orientation_button, 1, 1)
        self.adjust_button = QPushButton("Görsel ayarları…")
        self.adjust_button.clicked.connect(self.choose_image_adjustments)
        editing.addWidget(self.adjust_button, 2, 0, 1, 2)
        wheel_layout.addLayout(editing)
        layout.addWidget(self.wheel)
        self.wheel.hide()

        self.images_pdf_button = QPushButton("Görsellerden PDF…")
        self.images_pdf_button.clicked.connect(self.choose_images_for_pdf)
        layout.addWidget(self.images_pdf_button)

        self.qr_button = QPushButton("QR kodu oku…")
        self.qr_button.clicked.connect(self.choose_qr)
        layout.addWidget(self.qr_button)

        self.image_ocr_button = QPushButton("Görseldeki yazıyı oku (OCR)…")
        self.image_ocr_button.clicked.connect(self.choose_image_ocr)
        layout.addWidget(self.image_ocr_button)
        layout.addStretch()

    def build_pdf_tools(self) -> None:
        layout = QVBoxLayout(self.pdf_tab)
        self.pdf_button = QPushButton("PDF birleştir…")
        self.pdf_button.clicked.connect(lambda: self.choose_pdfs())
        layout.addWidget(self.pdf_button)

        self.pages_button = QPushButton("PDF’den sayfa çıkar…")
        self.pages_button.clicked.connect(self.choose_pages)
        layout.addWidget(self.pages_button)

        self.pdf_rotate_button = QPushButton("PDF sayfalarını döndür…")
        self.pdf_rotate_button.clicked.connect(self.choose_pdf_rotate)
        layout.addWidget(self.pdf_rotate_button)

        self.pdf_render_button = QPushButton("PDF’yi görsele dönüştür…")
        self.pdf_render_button.clicked.connect(self.choose_pdf_render)
        layout.addWidget(self.pdf_render_button)

        self.pdf_text_button = QPushButton("PDF’den metin çıkar…")
        self.pdf_text_button.clicked.connect(self.choose_pdf_text)
        layout.addWidget(self.pdf_text_button)

        self.pdf_ocr_button = QPushButton("Taranmış PDF’yi oku (OCR)…")
        self.pdf_ocr_button.clicked.connect(self.choose_pdf_ocr)
        layout.addWidget(self.pdf_ocr_button)

        self.pdf_qr_button = QPushButton("PDF’de QR kodu ara…")
        self.pdf_qr_button.clicked.connect(self.choose_pdf_qr)
        layout.addWidget(self.pdf_qr_button)
        layout.addStretch()

    def build_video_tools(self) -> None:
        layout = QVBoxLayout(self.video_tab)
        self.video_convert_button = QPushButton("Videoyu dönüştür…")
        self.video_convert_button.clicked.connect(self.choose_video_conversion)
        layout.addWidget(self.video_convert_button)

        self.audio_button = QPushButton("Videodan MP3 çıkar…")
        self.audio_button.clicked.connect(self.choose_video)
        layout.addWidget(self.audio_button)

        self.mute_button = QPushButton("Video sesini kaldır…")
        self.mute_button.clicked.connect(self.choose_mute)
        layout.addWidget(self.mute_button)

        self.frame_button = QPushButton("Videodan kare al…")
        self.frame_button.clicked.connect(self.choose_frame)
        layout.addWidget(self.frame_button)

        self.trim_button = QPushButton("Videoyu kes…")
        self.trim_button.clicked.connect(self.choose_trim)
        layout.addWidget(self.trim_button)
        layout.addStretch()

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
        self.select_files(paths)

    def select_files(self, paths: tuple[Path, ...]) -> bool:
        if not paths:
            return False
        if len(paths) == 1:
            self.select_file(paths[0])
        elif all(path.suffix.lower() == ".pdf" for path in paths):
            self.select_pdf(paths[0])
            QTimer.singleShot(0, lambda: self.choose_pdfs(paths))
        else:
            return self.select_batch(paths)
        return True

    def select_batch(self, paths: tuple[Path, ...]) -> bool:
        if any(path.suffix.lower() in (*VIDEO_EXTENSIONS, ".pdf") for path in paths):
            self.status.setText("Toplu dönüştürme için yalnızca görselleri seç.")
            return False
        self.source = None
        self.batch_sources = paths
        self.drop_zone.setText(f"{len(paths)} görsel seçildi")
        self.tools.setCurrentWidget(self.image_tab)
        self.wheel.show()
        self.resize_button.hide()
        self.crop_button.hide()
        self.compress_button.hide()
        self.orientation_button.hide()
        self.adjust_button.hide()
        self.audio_button.setText("Videodan MP3 çıkar…")
        self.clear_result()
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
        self.orientation_button.show()
        self.adjust_button.show()
        self.tools.setCurrentWidget(self.image_tab)
        self.drop_zone.setText(source.name)
        self.wheel.show()
        self.audio_button.setText("Videodan MP3 çıkar…")
        self.clear_result()

    def select_video(self, source: Path) -> None:
        self.batch_sources = ()
        self.source = source
        self.tools.setCurrentWidget(self.video_tab)
        self.drop_zone.setText(source.name)
        self.wheel.hide()
        self.audio_button.setText("MP3 olarak kaydet")
        self.clear_result()

    def select_pdf(self, source: Path) -> None:
        self.batch_sources = ()
        self.source = source
        self.tools.setCurrentWidget(self.pdf_tab)
        self.drop_zone.setText(source.name)
        self.wheel.hide()
        self.audio_button.setText("Videodan MP3 çıkar…")
        self.clear_result()

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

    def choose_video_conversion(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_video_source("Dönüştürülecek videoyu seç")
            if source is None:
                return
            formats = list(VIDEO_EXPORT_OPTIONS)
            default = formats.index("WebM" if source.suffix.lower() == ".mp4" else "MP4")
            output_format, accepted = QInputDialog.getItem(
                self, "Videoyu dönüştür", "Çıktı biçimi", formats, default, False
            )
            if accepted:
                operation = partial(convert_video, source, output_format)
                self.start_job(operation, "Video dönüştürülüyor…")
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_video(self) -> None:
        self.run_video_action("Sesini çıkaracağın videoyu seç", extract_mp3, "MP3 hazırlanıyor…")

    def choose_mute(self) -> None:
        self.run_video_action(
            "Sessiz kopyası oluşturulacak videoyu seç", mute_video, "Sessiz video hazırlanıyor…"
        )

    def run_video_action(
        self, title: str, operation: Callable[[Path], Path], status: str
    ) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_video_source(title)
            if source is not None:
                self.start_job(partial(operation, source), status)
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
            dialog = VideoFrameDialog(source, self)
            try:
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    operation = partial(extract_frame, source, dialog.timestamp.text())
                    self.start_job(operation, "Video karesi hazırlanıyor…")
            finally:
                dialog.deleteLater()
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
            dialog = VideoTrimDialog(source, self)
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
        if self.select_files(local_drop_paths(event)):
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

    def image_preview(self, source: Path) -> Image.Image | None:
        try:
            return read_preview_image(source)
        except Image.DecompressionBombError:
            self.status.setText("Görsel güvenli işlem boyutunu aşıyor.")
        except (OSError, ValueError) as error:
            self.status.setText(f"Önizleme açılamadı: {error}")
        return None

    def choose_crop(self) -> None:
        source = self.source
        if source is None or self.job is not None:
            return
        preview = self.image_preview(source)
        if preview is None:
            return

        self.set_drag_monitor_enabled(False)
        dialog = CropDialog(to_qimage(preview), self)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                bounds = dialog.preview.bounds()
                if bounds is not None:
                    operation = partial(convert_image, source, None, crop_bounds=bounds)
                    self.start_job(operation, "Görsel kırpılıyor…")
        finally:
            dialog.deleteLater()
            self.set_drag_monitor_enabled(self.job is None)

    def choose_orientation(self) -> None:
        source = self.source
        if source is None or self.job is not None:
            return
        preview = self.image_preview(source)
        if preview is None:
            return

        self.set_drag_monitor_enabled(False)
        dialog = OrientationDialog(to_qimage(preview), self)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                operation = partial(convert_image, source, None, orientation=dialog.orientation)
                self.start_job(operation, "Düzenlenen görsel kaydediliyor…")
        finally:
            dialog.deleteLater()
            self.set_drag_monitor_enabled(self.job is None)

    def choose_image_adjustments(self) -> None:
        source = self.source
        if source is None or self.job is not None:
            return
        preview = self.image_preview(source)
        if preview is None:
            return

        self.set_drag_monitor_enabled(False)
        dialog = ImageAdjustDialog(preview, self)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                operation = partial(adjust_image, source, dialog.settings())
                self.start_job(operation, "Ayarlanan görsel kaydediliyor…")
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

    def choose_image_source(self, title: str) -> Path | None:
        source = self.source
        if source is not None and not self.wheel.isHidden():
            return source

        filename, _ = QFileDialog.getOpenFileName(self, title)
        if not filename:
            return None
        source = Path(filename)
        self.select_image(source)
        return source

    def choose_qr(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_image_source("QR kodu içeren görseli seç")
            if source is not None:
                self.start_job(
                    partial(read_qr_codes, source),
                    "QR kodu aranıyor…",
                    on_success=self.show_qr_result,
                )
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_image_ocr(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_image_source("Yazısını okuyacağın görseli seç")
            if source is not None:
                self.start_job(partial(ocr_image, source), "Görseldeki yazı okunuyor…")
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_pdf_qr(self) -> None:
        self.run_pdf_page_selection(
            "PDF’de QR kodu ara",
            "PDF sayfalarında QR kodu aranıyor…",
            read_pdf_qr_codes,
            allow_all=True,
            on_success=self.show_qr_result,
        )

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

    def choose_pdf_source(self) -> Path | None:
        source = self.source
        if source is not None and source.suffix.lower() == ".pdf":
            return source

        filename, _ = QFileDialog.getOpenFileName(
            self, "PDF seç", filter="PDF (*.pdf *.PDF)"
        )
        if not filename:
            return None
        source = Path(filename)
        self.select_pdf(source)
        return source

    def choose_pages(self) -> None:
        self.run_pdf_page_selection(
            "PDF’den sayfa çıkar", "Sayfalar çıkarılıyor…", extract_pages
        )

    def choose_pdf_text(self) -> None:
        self.run_pdf_page_selection(
            "PDF’den metin çıkar",
            "PDF metni çıkarılıyor…",
            extract_pdf_text,
            allow_all=True,
        )

    def choose_pdf_ocr(self) -> None:
        self.run_pdf_page_selection(
            "Taranmış PDF’yi oku",
            "Taranmış sayfalar okunuyor…",
            ocr_pdf,
            allow_all=True,
        )

    def run_pdf_page_selection(
        self,
        title: str,
        status: str,
        operation: Callable[[Path, str], FileResult],
        *,
        allow_all: bool = False,
        on_success: Callable[[str], None] | None = None,
    ) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_pdf_source()
            if source is None:
                return
            hint = (
                "Tüm sayfalar için boş bırak veya 1, 3-5 gibi bir seçim yaz."
                if allow_all
                else "Sayfa numaraları veya aralıkları (ör. 1, 3-5)"
            )
            selection, accepted = QInputDialog.getText(
                self, title, f"{source.name}\n{hint}"
            )
            if accepted:
                self.start_job(partial(operation, source, selection), status, on_success=on_success)
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_pdf_rotate(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_pdf_source()
            if source is None:
                return
            dialog = PdfRotateDialog(source.name, self)
            try:
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    operation = partial(
                        rotate_pages, source, dialog.pages.text(), dialog.direction.currentData()
                    )
                    self.start_job(operation, "PDF sayfaları döndürülüyor…")
            finally:
                dialog.deleteLater()
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_pdf_render(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_pdf_source()
            if source is None:
                return
            dialog = PdfRenderDialog(source.name, self)
            try:
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    operation = partial(
                        render_pdf_pages,
                        source,
                        dialog.pages.text(),
                        dialog.output_format.currentText(),
                    )
                    self.start_job(operation, "PDF sayfaları görsele dönüştürülüyor…")
            finally:
                dialog.deleteLater()
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

    def clear_result(self) -> None:
        self.status.clear()
        self.show_output_actions(())

    @Slot(object)
    def show_output_actions(self, paths: tuple[Path, ...]) -> None:
        self.output_paths = paths
        self.output_actions.setVisible(bool(paths))
        self.open_output_button.setVisible(len(paths) == 1)
        folder_count = len({path.parent for path in paths})
        label = "Çıktı klasörü seç…" if folder_count > 1 else "Çıktı klasörünü aç"
        self.open_folder_button.setText(label)

    def open_output(self) -> None:
        if len(self.output_paths) == 1:
            self.open_local_path(self.output_paths[0])

    def open_output_folder(self) -> None:
        folders = tuple(dict.fromkeys(path.parent for path in self.output_paths))
        if len(folders) == 1:
            self.open_local_path(folders[0])
        elif folders:
            menu = QMenu(self)
            for folder in folders:
                action = menu.addAction(str(folder).replace("&", "&&"))
                action.setData(str(folder))
            position = self.open_folder_button.mapToGlobal(
                QPoint(0, self.open_folder_button.height())
            )
            selected = menu.exec(position)
            if selected is not None:
                self.open_local_path(Path(selected.data()))
            menu.deleteLater()

    def open_local_path(self, path: Path) -> None:
        if not path.exists():
            self.status.setText(f"Dosya veya klasör bulunamadı: {path.name}")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.absolute()))):
            self.status.setText(f"Açılamadı: {path.name}")

    def start_job(
        self,
        operation: Callable[[], FileResult],
        status: str,
        *,
        on_success: Callable[[str], None] | None = None,
    ) -> None:
        self.set_drag_monitor_enabled(False)
        self.show_output_actions(())
        self.status.setText(status)
        self.set_file_controls_enabled(False)
        self.job = FileJob(operation, self)
        self.job.succeeded.connect(on_success or self.status.setText)
        self.job.outputs_ready.connect(self.show_output_actions)
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
        self.pdf_rotate_button.setEnabled(enabled)
        self.pdf_render_button.setEnabled(enabled)
        self.pdf_text_button.setEnabled(enabled)
        self.pdf_ocr_button.setEnabled(enabled)
        self.pdf_qr_button.setEnabled(enabled)
        self.images_pdf_button.setEnabled(enabled)
        self.video_convert_button.setEnabled(enabled)
        self.audio_button.setEnabled(enabled)
        self.mute_button.setEnabled(enabled)
        self.frame_button.setEnabled(enabled)
        self.trim_button.setEnabled(enabled)
        self.qr_button.setEnabled(enabled)
        self.image_ocr_button.setEnabled(enabled)

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
    window.select_files(paths)


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
