"""Görsellere işaret ve opak gizleme alanı ekler."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from uvaia_app.ui.crop_dialog import CropPreview
from uvaia_app.core.image_conversion import read_still_image
from uvaia_app.ui.image_preview import to_qimage
from uvaia_app.core.output_files import save_new_file


@dataclass(frozen=True)
class Mark:
    tool: str
    start: tuple[float, float]
    end: tuple[float, float]
    text: str = ""


def draw_marks(source: Image.Image, marks: list[Mark]) -> Image.Image:
    image = source.copy()
    draw = ImageDraw.Draw(image)
    stroke = max(2, round(min(image.size) * .008))
    ink = "#ff582b"
    for mark in marks:
        x1, y1 = (round(value * size) for value, size in zip(mark.start, image.size, strict=True))
        x2, y2 = (round(value * size) for value, size in zip(mark.end, image.size, strict=True))
        box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        if mark.tool == "Gizle":
            draw.rectangle(box, fill="#000000")
        elif mark.tool == "Kutu":
            draw.rectangle(box, outline=ink, width=stroke)
        elif mark.tool == "Metin":
            font = ImageFont.truetype("DejaVuSans.ttf", max(1, box[3] - box[1]))
            draw.text(box[:2], mark.text, font=font, fill=ink, stroke_width=max(1, stroke // 3),
                      stroke_fill="#231121")
        elif mark.tool == "Ok":
            angle = atan2(y2 - y1, x2 - x1)
            length = stroke * 4
            draw.line((x1, y1, x2, y2), fill=ink, width=stroke)
            draw.polygon([(x2, y2), *[
                (x2 - length * cos(angle + offset), y2 - length * sin(angle + offset))
                for offset in (-.5, .5)
            ]], fill=ink)
    return image


def save_markup(source: Path, marks: list[Mark]) -> Path:
    original, _ = read_still_image(source)
    rendered = draw_marks(original, marks)
    clean = Image.frombytes("RGBA", rendered.size, rendered.tobytes())
    return save_new_file(source.with_name(f"{source.stem}-isaretli.png"),
                         lambda stream: clean.save(stream, format="PNG"))


class MarkupDialog(QDialog):
    def __init__(self, image: Image.Image, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Görseli işaretle")
        self.resize(690, 540)
        self.image = image
        self.marks: list[Mark] = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Bir araç seç, görselde alanı sürükle ve Uygula’ya bas."))
        self.preview = CropPreview(to_qimage(image), self)
        self.preview.setAccessibleName("İşaretleme önizlemesi")
        layout.addWidget(self.preview, 1)
        row = QHBoxLayout()
        self.tool = QComboBox()
        self.tool.addItems(["Ok", "Kutu", "Metin", "Gizle"])
        row.addWidget(self.tool)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Eklenecek metin")
        self.text.setMaxLength(500)
        row.addWidget(self.text, 1)
        apply = QPushButton("Uygula")
        apply.clicked.connect(self.add_mark)
        row.addWidget(apply)
        undo = QPushButton("Geri al")
        undo.clicked.connect(self.undo)
        row.addWidget(undo)
        layout.addLayout(row)
        buttons = QDialogButtonBox()
        self.save = buttons.addButton("PNG kopyasını kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.tool.currentTextChanged.connect(lambda name: self.text.setEnabled(name == "Metin"))
        self.text.setEnabled(False)
        self.save.setEnabled(False)

    def add_mark(self) -> None:
        start, end = self.preview.start, self.preview.end
        tool = self.tool.currentText()
        if start is None or end is None or start == end or (tool == "Metin" and not self.text.text().strip()):
            return
        self.marks.append(Mark(tool, (start.x(), start.y()), (end.x(), end.y()), self.text.text()))
        self.refresh()

    def undo(self) -> None:
        if self.marks:
            self.marks.pop()
            self.refresh()

    def refresh(self) -> None:
        self.preview.start = self.preview.end = None
        self.preview.image = to_qimage(draw_marks(self.image, self.marks))
        self.preview.update()
        self.save.setEnabled(bool(self.marks))
