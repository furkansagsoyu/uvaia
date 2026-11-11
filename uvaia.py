"""Uvaia'nın Qt masaüstü arayüzü."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Xlib import error as x11_error

from drag_wheel import DragWheel, WHEEL_POSITIONS, WheelMonitor, accept_copy, local_drop_path
from image_conversion import FORMATS, convert_image

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


class Conversion(QThread):
    """Dönüştürmeyi pencereyi dondurmadan yürütür."""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, source: Path, output_format: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.source = source
        self.output_format = output_format

    def run(self) -> None:
        try:
            output = convert_image(self.source, self.output_format)
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
        self.job: Conversion | None = None
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

        self.drop_zone = QLabel("Bir görseli buraya bırak")
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
        self.wheel.hide()
        layout.addWidget(self.wheel)

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
        self.drop_zone.setText("Bir görseli buraya bırak veya sürüklerken Shift'e bas")

    def convert_drop(self, source: Path, output_format: str) -> None:
        self.select_image(source)
        self.showNormal()
        self.raise_()
        self.convert(output_format)

    def choose_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Görsel seç")
        if filename:
            self.select_image(Path(filename))

    def select_image(self, source: Path) -> None:
        self.source = source
        self.drop_zone.setText(source.name)
        self.wheel.show()
        self.status.clear()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.job is None and local_drop_path(event) is not None:
            accept_copy(event)

    def dropEvent(self, event: QDropEvent) -> None:
        source = local_drop_path(event)
        if self.job is None and source is not None and source.is_file():
            self.select_image(source)
            accept_copy(event)

    def convert(self, output_format: str) -> None:
        if self.source is None or self.job is not None:
            return
        if self.monitor is not None:
            self.monitor.enabled = False
            self.monitor.wheel.hide()
        self.status.setText("Dönüştürülüyor…")
        self.pick.setEnabled(False)
        self.wheel.setEnabled(False)
        self.job = Conversion(self.source, output_format, self)
        self.job.succeeded.connect(lambda name: self.status.setText(f"Kaydedildi: {name}"))
        self.job.failed.connect(lambda message: self.status.setText(f"Dönüştürülemedi: {message}"))
        self.job.finished.connect(self.conversion_finished)
        self.job.finished.connect(self.job.deleteLater)
        self.job.start()

    def conversion_finished(self) -> None:
        self.job = None
        if self.monitor is not None:
            self.monitor.enabled = True
        self.pick.setEnabled(True)
        self.wheel.setEnabled(True)

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
            window.select_image(path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
