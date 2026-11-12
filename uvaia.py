"""Uvaia'nın Qt masaüstü arayüzü."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices, QDragEnterEvent, QDragLeaveEvent, QDropEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from Xlib import error as x11_error

from archive_tools import create_zip, extract_zip
from audio_tools import AUDIO_EXPORT_OPTIONS, AUDIO_EXTENSIONS, convert_audio, trim_audio
from audio_trim_dialog import AudioTrimDialog
from compression_dialog import CompressionDialog
from crop_dialog import CropDialog
from drag_wheel import (
    WHEEL_POSITIONS,
    DragWheel,
    WheelMonitor,
    accept_copy,
    local_drop_paths,
    offers_file_copy,
    wheel_formats,
)
from file_order_dialog import FileOrderDialog
from image_adjust_dialog import ImageAdjustDialog
from image_conversion import FORMATS, adjust_image, compress_image, convert_image, convert_images
from image_metadata import inspect_image, save_clean_png
from image_preview import read_preview_image, to_qimage
from job_progress import JobCancelled, JobProgress
from ocr_tools import OCR_DPI, OCR_EXPORT_FORMATS, ocr_image, ocr_pdf
from orientation_dialog import OrientationDialog
from output_files import SavedOutputs
from pdf_export_dialog import PdfExportDialog
from pdf_render import DPI, render_pdf_pages
from pdf_rotate_dialog import PdfRotateDialog
from pdf_split_dialog import PdfSplitDialog
from pdf_text import extract_pdf_text
from pdf_tools import extract_pages, images_to_pdf, merge_pdfs, rotate_pages, split_pdf
from qr_reader import read_pdf_qr_codes, read_qr_codes
from video_compression_dialog import VideoCompressionDialog
from video_frame_dialog import VideoFrameDialog
from video_tools import (
    VIDEO_EXPORT_OPTIONS,
    VIDEO_EXTENSIONS,
    change_video_speed,
    compress_video,
    convert_video,
    extract_frame,
    extract_mp3,
    mute_video,
    trim_video,
)
from video_trim_dialog import VideoTrimDialog

ICON_PATH = Path(__file__).resolve().parent / "assets" / "uvaia.png"

STYLE = """
QWidget { background: #281323; color: #fff1db; font-size: 14px; }
QLabel#title { font-size: 34px; font-weight: 750; }
QLabel#status, QLabel#dropHint { color: #d8bdcf; }
QLabel#dropZone { font-size: 19px; font-weight: 650; }
QFrame#dropCard { background: #391e34; border: 1px dashed #a86e97; border-radius: 17px; }
QFrame#dropCard[dragging="true"] { background: #4b2841; border-color: #ff9b39; }
QFrame#dropCard QLabel { background: transparent; }
QPushButton { background: #43263d; border: 1px solid #774a6d; border-radius: 9px;
    min-height: 24px; padding: 8px 13px; }
QPushButton#pick, QPushButton[format="true"] { background: #ff9b39; color: #341023;
    border-color: #ff9b39; font-weight: 700; }
QPushButton[format="true"] { border-radius: 19px; }
QPushButton:hover { border-color: #ff9b39; }
QPushButton#pick:hover, QPushButton[format="true"]:hover { background: #ffc447; }
QPushButton:focus { border-color: #fff2c5; }
QPushButton:disabled, QPushButton#pick:disabled, QPushButton[format="true"]:disabled {
    color: #c8adbd; background: #3a2636; border-color: #62465a; }
QTabWidget::pane { border: 1px solid #6a4260; border-radius: 11px; }
QTabBar::tab { padding: 9px 15px; border: 1px solid transparent;
    border-bottom: 2px solid transparent; color: #d8bdcf; }
QTabBar::tab:selected { color: #ffd363; border-bottom-color: #ff9b39; }
QTabBar::tab:hover { background: #43263d; }
QTabBar::tab:focus { border-top-color: #d8bdcf; }
QProgressBar { border: 1px solid #774a6d; border-radius: 7px; text-align: center; }
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QListWidget {
    background: #33192e; border: 1px solid #774a6d; border-radius: 6px;
    selection-background-color: #17685e; selection-color: #fff1db;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus, QListWidget:focus {
    border-color: #ff9b39;
}
QProgressBar::chunk { background: #17685e; border-radius: 6px; }
"""


FileResult = Path | SavedOutputs | str


class FileJob(QThread):
    """Dosya işlemini pencereyi dondurmadan yürütür."""

    succeeded = Signal(str)
    outputs_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, operation: Callable[[], FileResult], parent: QWidget) -> None:
        super().__init__(parent)
        self.operation = operation

    def run(self) -> None:
        try:
            output = self.operation()
        except JobCancelled:
            self.cancelled.emit()
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


class ProgressFileJob(FileJob):
    progress_changed = Signal(int, int)

    def __init__(self, operation: Callable[[JobProgress], FileResult], parent: QWidget) -> None:
        super().__init__(lambda: operation(self.progress_context()), parent)

    def progress_context(self) -> JobProgress:
        return JobProgress(self.progress_changed.emit, self.isInterruptionRequested)


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
        self.setMinimumWidth(440)
        self.resize(570, 430)
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        icon = QIcon(str(ICON_PATH))
        self.setWindowIcon(icon)
        brand = QLabel()
        brand.setPixmap(icon.pixmap(48, 48))
        header.addWidget(brand)
        title = QLabel("Uvaia")
        title.setObjectName("title")
        header.addWidget(title, 1)
        layout.addLayout(header)

        self.drop_card = QFrame()
        self.drop_card.setObjectName("dropCard")
        drop_layout = QVBoxLayout(self.drop_card)
        drop_layout.setContentsMargins(18, 19, 18, 19)
        drop_layout.setSpacing(8)
        self.drop_zone = QLabel("Dosyaları buraya bırak")
        self.drop_zone.setObjectName("dropZone")
        self.drop_zone.setTextFormat(Qt.TextFormat.PlainText)
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.setWordWrap(True)
        drop_layout.addWidget(self.drop_zone)
        self.drop_hint = QLabel("Görsel, PDF, video, ses ve ZIP")
        self.drop_hint.setObjectName("dropHint")
        self.drop_hint.setWordWrap(True)
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.drop_hint)
        self.pick = QPushButton("Dosya seç…")
        self.pick.setObjectName("pick")
        self.pick.setShortcut(QKeySequence("Ctrl+O"))
        self.pick.setToolTip("Dosya seç (Ctrl+O)")
        self.pick.clicked.connect(self.choose_image)
        drop_layout.addWidget(self.pick, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.drop_card)

        self.tools = QTabWidget()
        self.tools.setAccessibleName("Dosya araçları")
        layout.addWidget(self.tools)
        self.image_tab = QWidget()
        self.pdf_tab = QWidget()
        self.video_tab = QWidget()
        self.audio_tab = QWidget()
        self.archive_tab = QWidget()
        self.tools.addTab(self.image_tab, "Görsel")
        self.tools.addTab(self.pdf_tab, "PDF")
        self.tools.addTab(self.video_tab, "Video")
        self.tools.addTab(self.audio_tab, "Ses")
        self.tools.addTab(self.archive_tab, "Arşiv")
        self.build_image_tools()
        self.build_pdf_tools()
        self.build_video_tools()
        self.build_audio_tools()
        self.build_archive_tools()

        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.progress_actions = QWidget()
        progress_layout = QHBoxLayout(self.progress_actions)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.job_progress = QProgressBar()
        self.job_progress.setAccessibleName("İşlem ilerlemesi")
        progress_layout.addWidget(self.job_progress, 1)
        self.cancel_job_button = QPushButton("İptal et")
        self.cancel_job_button.clicked.connect(self.cancel_job)
        progress_layout.addWidget(self.cancel_job_button)
        self.progress_actions.hide()
        layout.addWidget(self.progress_actions)

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

        actions = QGridLayout()
        self.images_pdf_button = QPushButton("Görsellerden PDF…")
        self.images_pdf_button.clicked.connect(self.choose_images_for_pdf)
        actions.addWidget(self.images_pdf_button, 0, 0)

        self.qr_button = QPushButton("QR kodu oku…")
        self.qr_button.clicked.connect(self.choose_qr)
        actions.addWidget(self.qr_button, 0, 1)

        self.image_ocr_button = QPushButton("Görseldeki yazıyı oku (OCR)…")
        self.image_ocr_button.clicked.connect(self.choose_image_ocr)
        actions.addWidget(self.image_ocr_button, 1, 0)

        self.metadata_button = QPushButton("Görsel bilgileri…")
        self.metadata_button.clicked.connect(self.choose_image_metadata)
        actions.addWidget(self.metadata_button, 1, 1)
        layout.addLayout(actions)
        layout.addStretch()

    def build_pdf_tools(self) -> None:
        layout = QGridLayout(self.pdf_tab)
        self.pdf_button = QPushButton("PDF birleştir…")
        self.pdf_button.clicked.connect(lambda: self.choose_pdfs())
        layout.addWidget(self.pdf_button, 0, 0)

        self.pages_button = QPushButton("PDF’den sayfa çıkar…")
        self.pages_button.clicked.connect(self.choose_pages)
        layout.addWidget(self.pages_button, 0, 1)

        self.pdf_split_button = QPushButton("PDF’yi böl…")
        self.pdf_split_button.clicked.connect(self.choose_pdf_split)
        layout.addWidget(self.pdf_split_button, 1, 0)

        self.pdf_rotate_button = QPushButton("PDF sayfalarını döndür…")
        self.pdf_rotate_button.clicked.connect(self.choose_pdf_rotate)
        layout.addWidget(self.pdf_rotate_button, 1, 1)

        self.pdf_render_button = QPushButton("PDF’yi görsele dönüştür…")
        self.pdf_render_button.clicked.connect(self.choose_pdf_render)
        layout.addWidget(self.pdf_render_button, 2, 0)

        self.pdf_text_button = QPushButton("PDF’den metin çıkar…")
        self.pdf_text_button.clicked.connect(self.choose_pdf_text)
        layout.addWidget(self.pdf_text_button, 2, 1)

        self.pdf_ocr_button = QPushButton("Taranmış PDF’yi oku (OCR)…")
        self.pdf_ocr_button.clicked.connect(self.choose_pdf_ocr)
        layout.addWidget(self.pdf_ocr_button, 3, 0)

        self.pdf_qr_button = QPushButton("PDF’de QR kodu ara…")
        self.pdf_qr_button.clicked.connect(self.choose_pdf_qr)
        layout.addWidget(self.pdf_qr_button, 3, 1)
        layout.setRowStretch(4, 1)

    def build_video_tools(self) -> None:
        layout = QGridLayout(self.video_tab)
        self.video_convert_button = QPushButton("Videoyu dönüştür…")
        self.video_convert_button.clicked.connect(self.choose_video_conversion)
        layout.addWidget(self.video_convert_button, 0, 0)

        self.video_compress_button = QPushButton("Videoyu sıkıştır…")
        self.video_compress_button.clicked.connect(self.choose_video_compression)
        layout.addWidget(self.video_compress_button, 0, 1)

        self.audio_button = QPushButton("Videodan MP3 çıkar…")
        self.audio_button.clicked.connect(self.choose_video)
        layout.addWidget(self.audio_button, 1, 0)

        self.mute_button = QPushButton("Video sesini kaldır…")
        self.mute_button.clicked.connect(self.choose_mute)
        layout.addWidget(self.mute_button, 1, 1)

        self.frame_button = QPushButton("Videodan kare al…")
        self.frame_button.clicked.connect(self.choose_frame)
        layout.addWidget(self.frame_button, 2, 0)

        self.trim_button = QPushButton("Videoyu kes…")
        self.trim_button.clicked.connect(self.choose_trim)
        layout.addWidget(self.trim_button, 2, 1)

        self.video_speed_button = QPushButton("Video hızını değiştir…")
        self.video_speed_button.clicked.connect(self.choose_video_speed)
        layout.addWidget(self.video_speed_button, 3, 0)
        layout.setRowStretch(4, 1)

    def build_audio_tools(self) -> None:
        layout = QVBoxLayout(self.audio_tab)
        self.audio_convert_button = QPushButton("Sesi dönüştür…")
        self.audio_convert_button.clicked.connect(self.choose_audio_conversion)
        layout.addWidget(self.audio_convert_button)

        self.audio_trim_button = QPushButton("Sesi kes…")
        self.audio_trim_button.clicked.connect(self.choose_audio_trim)
        layout.addWidget(self.audio_trim_button)
        layout.addStretch()

    def build_archive_tools(self) -> None:
        layout = QVBoxLayout(self.archive_tab)
        self.zip_create_button = QPushButton("ZIP oluştur…")
        self.zip_create_button.clicked.connect(self.choose_zip_create)
        layout.addWidget(self.zip_create_button)

        self.zip_extract_button = QPushButton("ZIP’i aç…")
        self.zip_extract_button.clicked.connect(self.choose_zip_extract)
        layout.addWidget(self.zip_extract_button)
        layout.addStretch()

    def start_drag_monitor(self) -> None:
        if QApplication.platformName() != "xcb":
            return
        wheel = DragWheel(QIcon(str(ICON_PATH)))
        try:
            self.monitor = WheelMonitor(self, wheel)
        except x11_error.DisplayError:
            return
        wheel.file_dropped.connect(self.convert_drop)
        QApplication.instance().aboutToQuit.connect(self.monitor.shutdown)
        self.drop_hint.setText("Görsel, PDF, video, ses ve ZIP · Dönüştürme çarkı: Shift")

    def convert_drop(self, paths: tuple[Path, ...], output_format: str) -> None:
        if self.job is not None or output_format not in wheel_formats(paths):
            return
        self.showNormal()
        self.raise_()
        if len(paths) > 1:
            if self.select_batch(paths):
                self.convert(output_format)
            return

        source = paths[0]
        self.select_file(source)
        extension = source.suffix.lower()
        if extension in VIDEO_EXTENSIONS:
            if output_format == "MP3":
                self.start_job(partial(extract_mp3, source), "MP3 hazırlanıyor…")
            else:
                self.start_progress_job(
                    lambda progress: convert_video(source, output_format, progress=progress),
                    "Video dönüştürülüyor…",
                )
        elif extension in AUDIO_EXTENSIONS:
            self.start_progress_job(
                lambda progress: convert_audio(source, output_format, progress=progress),
                "Ses dönüştürülüyor…",
            )
        elif extension == ".pdf":
            self.start_progress_job(
                lambda progress: render_pdf_pages(source, "", output_format, progress=progress),
                "PDF sayfaları görsele dönüştürülüyor…",
                unit="sayfa",
            )
        else:
            self.convert(output_format)

    def choose_image(self) -> None:
        self.set_drag_monitor_enabled(False)
        try:
            filenames, _ = QFileDialog.getOpenFileNames(self, "Dosya seç")
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
        if any(path.suffix.lower() in (*VIDEO_EXTENSIONS, *AUDIO_EXTENSIONS, ".pdf", ".zip") for path in paths):
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
        elif extension == ".zip":
            self.select_tool_file(source, self.archive_tab)
        elif extension in AUDIO_EXTENSIONS:
            self.select_tool_file(source, self.audio_tab)
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
        self.select_tool_file(source, self.video_tab)
        self.audio_button.setText("MP3 olarak kaydet")

    def select_pdf(self, source: Path) -> None:
        self.select_tool_file(source, self.pdf_tab)

    def select_tool_file(self, source: Path, tab: QWidget) -> None:
        self.batch_sources = ()
        self.source = source
        self.tools.setCurrentWidget(tab)
        self.drop_zone.setText(source.name)
        self.wheel.hide()
        self.audio_button.setText("Videodan MP3 çıkar…")
        self.clear_result()

    def choose_audio_source(self, title: str) -> Path | None:
        source = self.source
        if source is not None and source.suffix.lower() in AUDIO_EXTENSIONS:
            return source
        extensions = " ".join(f"*{ext} *{ext.upper()}" for ext in AUDIO_EXTENSIONS)
        filename, _ = QFileDialog.getOpenFileName(
            self, title, filter=f"Ses ({extensions})"
        )
        if not filename:
            return None
        source = Path(filename)
        self.select_tool_file(source, self.audio_tab)
        return source

    def choose_audio_conversion(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_audio_source("Dönüştürülecek ses dosyasını seç")
            if source is None:
                return
            formats = list(AUDIO_EXPORT_OPTIONS)
            default = formats.index("WAV" if source.suffix.lower() == ".mp3" else "MP3")
            output_format, accepted = QInputDialog.getItem(
                self, "Sesi dönüştür", "Çıktı biçimi", formats, default, False
            )
            if accepted:
                self.start_progress_job(
                    lambda progress: convert_audio(source, output_format, progress=progress),
                    "Ses dönüştürülüyor…",
                )
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_audio_trim(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_audio_source("Kesilecek ses dosyasını seç")
            if source is None:
                return
            default = source.suffix.upper().lstrip(".")
            if default not in AUDIO_EXPORT_OPTIONS:
                default = "MP3"
            dialog = AudioTrimDialog(source.name, default, self)
            try:
                if dialog.exec() == QDialog.DialogCode.Accepted and dialog.interval is not None:
                    interval, output_format = dialog.interval, dialog.output_format.currentText()
                    self.start_progress_job(
                        lambda progress: trim_audio(
                            source, interval, output_format, progress=progress
                        ),
                        "Ses kesiti hazırlanıyor…",
                    )
            finally:
                dialog.deleteLater()
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_zip_create(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            filenames, _ = QFileDialog.getOpenFileNames(self, "ZIP’e eklenecek dosyaları seç")
            sources = tuple(dict.fromkeys(Path(filename) for filename in filenames))
            if sources:
                self.start_progress_job(
                    lambda progress: create_zip(sources, progress=progress),
                    "ZIP hazırlanıyor…",
                    unit="dosya",
                )
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_zip_extract(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.source
            if source is None or source.suffix.lower() != ".zip":
                filename, _ = QFileDialog.getOpenFileName(
                    self, "Açılacak ZIP’i seç", filter="ZIP (*.zip *.ZIP)"
                )
                if not filename:
                    return
                source = Path(filename)
                self.select_tool_file(source, self.archive_tab)
            self.start_progress_job(
                lambda progress: extract_zip(source, progress=progress),
                "ZIP açılıyor…",
                unit="öğe",
            )
        finally:
            self.set_drag_monitor_enabled(self.job is None)

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
                self.start_progress_job(
                    lambda progress: convert_video(source, output_format, progress=progress),
                    "Video dönüştürülüyor…",
                )
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_video_compression(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_video_source("Sıkıştırılacak videoyu seç")
            if source is None:
                return
            dialog = VideoCompressionDialog(source.name, self)
            try:
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    settings = dialog.settings()
                    self.start_progress_job(
                        lambda progress: compress_video(source, settings, progress=progress),
                        "Video sıkıştırılıyor…",
                    )
            finally:
                dialog.deleteLater()
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def choose_video_speed(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_video_source("Hızı değiştirilecek videoyu seç")
            if source is None:
                return
            speed, accepted = QInputDialog.getDouble(
                self, "Video hızını değiştir", "Oynatma hızı (×)", 1.25, 0.5, 2.0, 2
            )
            if accepted:
                self.start_progress_job(
                    lambda progress: change_video_speed(source, speed, progress=progress),
                    "Video hızı değiştiriliyor…",
                )
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
                    start, end = dialog.interval
                    self.start_progress_job(
                        lambda progress: trim_video(source, start, end, progress=progress),
                        "Video kesiti hazırlanıyor…",
                    )
            finally:
                dialog.deleteLater()
        finally:
            self.set_drag_monitor_enabled(self.job is None)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.job is None and offers_file_copy(event):
            self.set_drop_highlight(True)
            accept_copy(event)

    def set_drop_highlight(self, active: bool) -> None:
        self.drop_card.setProperty("dragging", active)
        self.drop_card.style().unpolish(self.drop_card)
        self.drop_card.style().polish(self.drop_card)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.set_drop_highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.set_drop_highlight(False)
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

    def choose_image_metadata(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_image_source("Bilgilerini görmek istediğin görseli seç")
            if source is None:
                return
            try:
                description = inspect_image(source)
            except Image.DecompressionBombError:
                self.status.setText("Görsel güvenli işlem boyutunu aşıyor.")
                return
            except (OSError, ValueError) as error:
                self.status.setText(f"Görsel bilgileri okunamadı: {error}")
                return
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Görsel bilgileri")
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.setText(description)
            save = dialog.addButton("Meta verisiz PNG kaydet", QMessageBox.ButtonRole.AcceptRole)
            dialog.addButton("Kapat", QMessageBox.ButtonRole.RejectRole)
            try:
                dialog.exec()
                if dialog.clickedButton() is save:
                    self.start_job(partial(save_clean_png, source), "Temiz PNG hazırlanıyor…")
            finally:
                dialog.deleteLater()
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
        choices = self.choose_pdf_export(
            title="Taranmış PDF’yi oku",
            formats=OCR_EXPORT_FORMATS,
            hint=f"Aranabilir PDF, {OCR_DPI} DPI sayfa görüntülerine metin katmanı ekler.",
            save_label="OCR çıktısını kaydet",
        )
        if choices is not None:
            self.start_progress_job(
                lambda progress: ocr_pdf(*choices, progress=progress),
                "Taranmış sayfalar okunuyor…",
                unit="sayfa",
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

    def choose_pdf_split(self) -> None:
        if self.job is not None:
            return
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_pdf_source()
            if source is None:
                return
            dialog = PdfSplitDialog(source.name, self)
            try:
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    selection, group_size = dialog.pages.text(), dialog.group_size.value()
                    self.start_progress_job(
                        lambda progress: split_pdf(source, selection, group_size, progress=progress),
                        "PDF bölünüyor…",
                        unit="bölüm",
                    )
            finally:
                dialog.deleteLater()
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
        choices = self.choose_pdf_export(
            title="PDF’yi görsele dönüştür",
            formats=("PNG", "JPG"),
            hint=f"Her sayfa {DPI} DPI ile ayrı bir görsele kaydedilir.",
            save_label="Görselleri kaydet",
        )
        if choices is not None:
            self.start_progress_job(
                lambda progress: render_pdf_pages(*choices, progress=progress),
                "PDF sayfaları görsele dönüştürülüyor…",
                unit="sayfa",
            )

    def choose_pdf_export(
        self,
        *,
        title: str,
        formats: tuple[str, ...],
        hint: str,
        save_label: str,
    ) -> tuple[Path, str, str] | None:
        if self.job is not None:
            return None
        self.set_drag_monitor_enabled(False)
        try:
            source = self.choose_pdf_source()
            if source is None:
                return None
            dialog = PdfExportDialog(
                source.name, self, title=title, formats=formats, hint=hint, save_label=save_label
            )
            try:
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    return source, dialog.pages.text(), dialog.output_format.currentText()
                return None
            finally:
                dialog.deleteLater()
        finally:
            self.set_drag_monitor_enabled(True)

    def convert(self, output_format: str | None, *, scale_percent: int | None = None) -> None:
        if self.job is not None:
            return
        if self.batch_sources and output_format is not None:
            sources = self.batch_sources
            self.start_progress_job(
                lambda progress: convert_images(sources, output_format, progress=progress),
                "Görseller dönüştürülüyor…",
                unit="görsel",
            )
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
        self.begin_job(FileJob(operation, self), status, on_success=on_success)

    def start_progress_job(
        self, operation: Callable[[JobProgress], FileResult], status: str, *, unit: str | None = None
    ) -> None:
        job = ProgressFileJob(operation, self)
        job.progress_changed.connect(self.update_job_progress)
        self.job_progress.setFormat(f"%v / %m {unit}" if unit else "%p%")
        self.job_progress.setRange(0, 0)
        self.cancel_job_button.setEnabled(True)
        self.progress_actions.show()
        self.begin_job(job, status)

    def begin_job(
        self, job: FileJob, status: str, *, on_success: Callable[[str], None] | None = None
    ) -> None:
        self.set_drag_monitor_enabled(False)
        self.show_output_actions(())
        self.status.setText(status)
        self.set_file_controls_enabled(False)
        self.job = job
        job.succeeded.connect(on_success or self.status.setText)
        job.outputs_ready.connect(self.show_output_actions)
        job.failed.connect(lambda message: self.status.setText(f"İşlem tamamlanamadı: {message}"))
        job.cancelled.connect(self.job_cancelled)
        job.finished.connect(self.job_finished)
        job.finished.connect(job.deleteLater)
        job.start()

    @Slot(int, int)
    def update_job_progress(self, completed: int, total: int) -> None:
        self.job_progress.setRange(0, total)
        self.job_progress.setValue(completed)

    def cancel_job(self) -> None:
        if isinstance(self.job, ProgressFileJob):
            self.job.requestInterruption()
            self.cancel_job_button.setEnabled(False)
            self.status.setText("İşlem iptal ediliyor…")

    @Slot()
    def job_cancelled(self) -> None:
        self.status.setText("İşlem iptal edildi.")

    def job_finished(self) -> None:
        self.job = None
        self.progress_actions.hide()
        self.set_drag_monitor_enabled(QApplication.activeModalWidget() is None)
        self.set_file_controls_enabled(True)

    def set_file_controls_enabled(self, enabled: bool) -> None:
        self.pick.setEnabled(enabled)
        self.wheel.setEnabled(enabled)
        self.pdf_button.setEnabled(enabled)
        self.pages_button.setEnabled(enabled)
        self.pdf_split_button.setEnabled(enabled)
        self.pdf_rotate_button.setEnabled(enabled)
        self.pdf_render_button.setEnabled(enabled)
        self.pdf_text_button.setEnabled(enabled)
        self.pdf_ocr_button.setEnabled(enabled)
        self.pdf_qr_button.setEnabled(enabled)
        self.images_pdf_button.setEnabled(enabled)
        self.video_convert_button.setEnabled(enabled)
        self.video_compress_button.setEnabled(enabled)
        self.audio_button.setEnabled(enabled)
        self.mute_button.setEnabled(enabled)
        self.frame_button.setEnabled(enabled)
        self.trim_button.setEnabled(enabled)
        self.video_speed_button.setEnabled(enabled)
        self.audio_convert_button.setEnabled(enabled)
        self.audio_trim_button.setEnabled(enabled)
        self.zip_create_button.setEnabled(enabled)
        self.zip_extract_button.setEnabled(enabled)
        self.qr_button.setEnabled(enabled)
        self.image_ocr_button.setEnabled(enabled)
        self.metadata_button.setEnabled(enabled)

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
    app.setDesktopFileName("io.github.furkansagsoyu.Uvaia")
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    window = Window()
    window.start_drag_monitor()
    window.show()
    open_startup_files(window, paths)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
