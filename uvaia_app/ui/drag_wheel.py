"""X11 sürüklemelerinde dosyaya uygun dönüştürme ve araç çarklarını açar."""

from __future__ import annotations

from math import cos, radians, sin
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import (
    QColor, QCursor, QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent,
    QIcon, QPaintEvent, QPainter, QPainterPath, QPen, QRegion,
)
from PySide6.QtWidgets import QApplication, QWidget
from Xlib import X, display, error

from uvaia_app.core.audio_tools import AUDIO_EXPORT_OPTIONS, AUDIO_EXTENSIONS
from uvaia_app.core.image_conversion import FORMATS
from uvaia_app.core.video_tools import VIDEO_EXPORT_OPTIONS, VIDEO_EXTENSIONS

IMAGE_TOOLS = (
    "Kırp", "Sıkıştır", "Döndür", "Boyutlandır", "Renk ayarı", "İşaretle",
    "Meta veri", "QR oku", "OCR", "PDF oluştur",
)
VIDEO_TOOLS = ("Kes", "Sıkıştır", "Kare al", "Sessize al", "Hız değiştir", "Birleştir")
AUDIO_TOOLS = ("Kes", "Sesi dengele", "Ses kanalı", "Birleştir")
PDF_TOOLS = ("Metin çıkar", "Böl", "Döndür", "Sayfa düzenle", "Sayfa çıkar", "QR oku", "OCR")

WHEEL_POSITIONS = ((0, 1), (2, 0), (2, 2))


def offers_file_copy(event: QDropEvent) -> bool:
    return bool(
        event.possibleActions() & Qt.DropAction.CopyAction and event.mimeData().hasUrls()
    )


def offered_paths(event: QDropEvent) -> tuple[Path, ...]:
    urls = event.mimeData().urls()
    if not all(url.isLocalFile() for url in urls):
        return ()
    return tuple(dict.fromkeys(Path(url.toLocalFile()) for url in urls))


def local_drop_paths(event: QDropEvent) -> tuple[Path, ...]:
    if not offers_file_copy(event):
        return ()
    paths = offered_paths(event)
    return paths if all(path.is_file() for path in paths) else ()


def file_family(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in (".pdf", ".zip"):
        return extension[1:]
    if extension in Image.registered_extensions():
        return "image"
    return ""


def shared_family(paths: tuple[Path, ...]) -> str:
    families = {file_family(path) for path in paths}
    return families.pop() if len(families) == 1 else ""


def wheel_formats(paths: tuple[Path, ...]) -> tuple[str, ...]:
    family = shared_family(paths)
    if family == "video":
        return (*VIDEO_EXPORT_OPTIONS, "MP3")
    if family == "audio":
        return tuple(AUDIO_EXPORT_OPTIONS)
    if family == "pdf":
        return "PNG", "JPG", "WebP", "TXT"
    if family == "image":
        Image.init()
        formats = tuple(name for name in FORMATS if name != "AVIF" or "AVIF" in Image.SAVE)
        return (*formats, "PDF")
    return ()


def wheel_tools(paths: tuple[Path, ...]) -> tuple[str, ...]:
    family = shared_family(paths)
    if len(paths) > 1:
        return {
            "video": ("Birleştir",), "audio": ("Birleştir",),
            "pdf": ("Birleştir",), "image": ("PDF oluştur",),
        }.get(family, ())
    return {
        "video": VIDEO_TOOLS, "audio": AUDIO_TOOLS, "pdf": PDF_TOOLS,
        "image": IMAGE_TOOLS, "zip": ("ZIP’i aç",),
    }.get(family, ())


def accept_copy(event: QDropEvent) -> None:
    event.setDropAction(Qt.DropAction.CopyAction)
    event.accept()


class X11Drag:
    """Dosya içeriğini almadan XDND sahipliğini ve tuş durumunu okur."""

    def __init__(self) -> None:
        self.connection = display.Display()
        self.root = self.connection.screen().root
        self.selection = self.connection.intern_atom("XdndSelection")

    def state(self) -> tuple[bool, bool, bool]:
        mask = self.root.query_pointer().mask
        dragging = bool(
            mask & X.Button1Mask and self.connection.get_selection_owner(self.selection)
        )
        return dragging, bool(mask & X.ShiftMask), bool(mask & X.ControlMask)

    def close(self) -> None:
        self.connection.close()


class DragWheel(QWidget):
    """Odak almadan açılan ve formatın üstüne bırakılan dosyaları ileten çark."""

    file_dropped = Signal(object, str)
    tool_dropped = Signal(object, str)

    SIZE = 416
    OUTER_RADIUS = 204
    INNER_RADIUS = 96

    def __init__(self, icon: QIcon) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setAccessibleName("Dosya dönüştürme çarkı")
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setMask(QRegion(self.rect(), QRegion.RegionType.Ellipse))
        self.icon = icon.pixmap(50, 50)
        self.center = QPointF(self.SIZE / 2, self.SIZE / 2)
        self.highlight: str | None = None
        self.shift_held = False
        self.copy_ready = False
        self.sectors: dict[str, tuple[float, QPainterPath]] = {}
        self.has_offer = False
        self.tools_mode = False

    def set_formats(self, formats: tuple[str, ...]) -> None:
        step = 360 / len(formats) if formats else 0
        self.sectors = {
            name: (angle, self.sector(angle, step - 8))
            for index, name in enumerate(formats)
            for angle in (90 + index * step,)
        }
        self.update()

    def circle(self, radius: float) -> QRectF:
        return QRectF(
            self.center.x() - radius, self.center.y() - radius, radius * 2, radius * 2
        )

    def sector(self, angle: float, sweep: float) -> QPainterPath:
        start = angle - sweep / 2
        outer, inner = self.circle(self.OUTER_RADIUS), self.circle(self.INNER_RADIUS)
        path = QPainterPath()
        path.arcMoveTo(outer, start)
        path.arcTo(outer, start, sweep)
        path.arcTo(inner, start + sweep, -sweep)
        path.closeSubpath()
        return path

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#281323"))
        painter.drawEllipse(self.circle(self.OUTER_RADIUS + 2))
        font = painter.font()
        font.setPixelSize(14 if self.tools_mode else 17)
        font.setBold(True)
        painter.setFont(font)

        radius = (self.OUTER_RADIUS + self.INNER_RADIUS) / 2
        for output_format, (angle, path) in self.sectors.items():
            selected = self.highlight == output_format
            painter.setPen(QPen(QColor("#ff9b39" if selected else "#774a6d"), 1.5))
            painter.setBrush(QColor("#ff9b39" if selected else "#43263d"))
            painter.drawPath(path)
            painter.setPen(QColor("#341023" if selected else "#fff1db"))
            x = self.center.x() + radius * cos(radians(angle))
            y = self.center.y() - radius * sin(radians(angle))
            label = output_format
            if len(self.sectors) >= 7 and len(label) > 9:
                label = label.replace(" ", "\n", 1)
            painter.drawText(QRectF(x - 51, y - 20, 102, 40), Qt.AlignmentFlag.AlignCenter, label)

        painter.setPen(QPen(QColor("#427c71"), 1.5))
        painter.setBrush(QColor("#203735"))
        painter.drawEllipse(self.circle(self.INNER_RADIUS - 6))
        painter.drawPixmap(QRect(self.SIZE // 2 - 25, self.SIZE // 2 - 51, 50, 50), self.icon)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor("#fff1db"))
        if not self.has_offer:
            hint = "Dosyayı çarka\ngetir"
        elif not self.sectors:
            hint = "Uygun seçenek\nbulunamadı"
        elif self.shift_held:
            hint = "Shift’i bırak\nFareyi tut"
        elif self.highlight and not self.copy_ready:
            hint = "İmleci dilimde\nbiraz oynat"
        else:
            hint = "Araca bırak" if self.tools_mode else "Biçime bırak"
        painter.drawText(QRectF(self.center.x() - 70, self.center.y(), 140, 43), Qt.AlignmentFlag.AlignCenter, hint)

    def open_near_cursor(self, *, tools_mode: bool = False) -> None:
        self.tools_mode = tools_mode
        self.has_offer = False
        self.set_formats(())
        self.set_highlight(None)
        cursor = QCursor.pos()
        screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        x = cursor.x() - self.width() // 2
        y = cursor.y() - self.height() // 2
        self.move(QPoint(
            max(bounds.left(), min(x, bounds.right() - self.width() + 1)),
            max(bounds.top(), min(y, bounds.bottom() - self.height() + 1)),
        ))
        self.show()
        self.raise_()

    def update_hint(self, shift: bool) -> None:
        if self.shift_held != shift:
            self.shift_held = shift
            self.update()

    def set_highlight(self, output_format: str | None, *, copy_ready: bool = False) -> None:
        if (self.highlight, self.copy_ready) != (output_format, copy_ready):
            self.highlight = output_format
            self.copy_ready = copy_ready
            self.update()

    def format_at(self, position: QPointF) -> str | None:
        return next(
            (output_format for output_format, (_, sector) in self.sectors.items() if sector.contains(position)),
            None,
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            self.has_offer = True
            self.set_formats(self.options(offered_paths(event)))
            self.set_highlight(self.format_at(event.position()), copy_ready=offers_file_copy(event))
            # Shift basılıyken Qt hedefi kaybetmemeli. Kopyalama koşulunu
            # hareket ve bırakma olaylarında denetle.
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        output_format = self.format_at(event.position()) if event.mimeData().hasUrls() else None
        copy_ready = offers_file_copy(event)
        self.set_highlight(output_format, copy_ready=copy_ready)
        if output_format and copy_ready:
            accept_copy(event)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.set_highlight(None)
        super().dragLeaveEvent(event)

    def options(self, paths: tuple[Path, ...]) -> tuple[str, ...]:
        return wheel_tools(paths) if self.tools_mode else wheel_formats(paths)

    def dropEvent(self, event: QDropEvent) -> None:
        output_format = self.format_at(event.position())
        paths = local_drop_paths(event) if output_format else ()
        if output_format and output_format in self.options(paths):
            accept_copy(event)
            self.hide()
            if self.tools_mode:
                self.tool_dropped.emit(paths, output_format)
            else:
                self.file_dropped.emit(paths, output_format)
        else:
            self.set_highlight(None)
            event.ignore()


class WheelMonitor(QTimer):
    """Sürükleme sırasında tuşla çarkı açar, sürükleme bitince kapatır."""

    def __init__(self, window: QWidget, wheel: DragWheel) -> None:
        super().__init__(window)
        self.wheel = wheel
        self.drag = X11Drag()
        self.enabled = True
        self.release_ticks = 0
        self.timeout.connect(self.poll)
        self.start(60)

    def poll(self) -> None:
        try:
            dragging, shift, control = self.drag.state()
        except (error.ConnectionClosedError, error.XError):
            self.stop()
            self.wheel.hide()
            return
        if dragging:
            self.release_ticks = 0
            if self.wheel.isVisible():
                self.wheel.update_hint(shift and not self.wheel.tools_mode)
            elif self.enabled and shift != control:
                self.wheel.update_hint(shift)
                self.wheel.open_near_cursor(tools_mode=control)
        elif self.wheel.isVisible():
            self.release_ticks += 1
            # Fare bırakıldıktan sonra Qt'ye XDND bırakma olayını teslim etme süresi tanı.
            if self.release_ticks >= 3:
                self.wheel.hide()

    def shutdown(self) -> None:
        self.stop()
        self.wheel.close()
        self.drag.close()
