"""PDF sayfalarını küçük resimlerle sıralar, döndürür ve çıkarır."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap, QTransform
from PySide6.QtWidgets import QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget
from pypdf import PdfWriter

from uvaia_app.ui.image_preview import to_qimage
from uvaia_app.core.output_files import save_new_file
from uvaia_app.core.pdf_render import open_pdf_document, page_image
from uvaia_app.core.pdf_tools import read_pdf

PAGE = Qt.ItemDataRole.UserRole
ROTATION = Qt.ItemDataRole.UserRole + 1


def organize_pdf(source: Path, pages: list[tuple[int, int]]) -> Path:
    if not pages:
        raise ValueError("En az bir sayfa bırak.")
    with read_pdf(source) as reader, PdfWriter() as writer:
        writer.append(reader, pages=[index for index, _ in pages])
        for page, (_, angle) in zip(writer.pages, pages, strict=True):
            page.rotation = (page.rotation + angle) % 360
        return save_new_file(source.with_name(f"{source.stem}-duzenlenmis.pdf"), writer.write)


class PdfOrganizer(QDialog):
    def __init__(self, source: Path, parent: QWidget) -> None:
        super().__init__(parent)
        self.document = open_pdf_document(source)
        self.thumbnails: dict[int, QPixmap] = {}
        self.next_page = 0
        self.setWindowTitle("PDF sayfalarını düzenle")
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Küçük resimleri sürükleyerek sırala. Düzenlemek için sayfaları seç."))
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.ListMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setIconSize(QSize(100, 120))
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDropIndicatorShown(True)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        layout.addWidget(self.list, 1)
        for index in range(len(self.document)):
            item = QListWidgetItem(f"Sayfa {index + 1}")
            item.setData(PAGE, index)
            item.setData(ROTATION, 0)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
            self.list.addItem(item)
        row = QHBoxLayout()
        for name, action in (("Yukarı", lambda: self.move_page(-1)), ("Aşağı", lambda: self.move_page(1)),
                             ("Sola döndür", lambda: self.rotate(-90)),
                             ("Sağa döndür", lambda: self.rotate(90)), ("Sayfayı çıkar", self.remove)):
            button = QPushButton(name)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)
        buttons = QDialogButtonBox()
        self.save = buttons.addButton("PDF kopyasını kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        self.save.setEnabled(self.list.count() > 0)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.load_thumbnail)
        self.timer.start(10)
        self.list.model().rowsMoved.connect(self.restart_thumbnails)

    def restart_thumbnails(self, *_args: object) -> None:
        self.next_page = 0
        self.timer.start(10)

    def move_page(self, offset: int) -> None:
        row = self.list.currentRow()
        if row >= 0 and 0 <= row + offset < self.list.count():
            self.list.insertItem(row + offset, self.list.takeItem(row))
            self.list.setCurrentRow(row + offset)
            self.restart_thumbnails()

    def load_thumbnail(self) -> None:
        if self.next_page >= self.list.count():
            self.timer.stop()
            return
        item = self.list.item(self.next_page)
        self.next_page += 1
        index = item.data(PAGE)
        if index not in self.thumbnails:
            try:
                with page_image(self.document, index, scale=.22) as image:
                    self.thumbnails[index] = QPixmap.fromImage(to_qimage(image.convert("RGBA")))
            except ValueError:
                return
        self.update_icon(item)

    def update_icon(self, item: QListWidgetItem) -> None:
        pixmap = self.thumbnails.get(item.data(PAGE))
        if pixmap is not None:
            angle = item.data(ROTATION)
            item.setIcon(QIcon(pixmap.transformed(QTransform().rotate(angle))))

    def rotate(self, angle: int) -> None:
        for item in self.list.selectedItems():
            item.setData(ROTATION, (item.data(ROTATION) + angle) % 360)
            self.update_icon(item)

    def remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self.next_page = 0
        self.timer.start(10)
        self.save.setEnabled(self.list.count() > 0)

    def pages(self) -> list[tuple[int, int]]:
        return [(self.list.item(row).data(PAGE), self.list.item(row).data(ROTATION))
                for row in range(self.list.count())]

    def close_document(self) -> None:
        self.timer.stop()
        self.document.close()
