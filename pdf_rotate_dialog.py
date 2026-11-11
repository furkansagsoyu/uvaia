"""Döndürülecek PDF sayfalarını ve yönü seçtirir."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class PdfRotateDialog(QDialog):
    def __init__(self, filename: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("PDF sayfalarını döndür")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        name = QLabel(filename)
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        layout.addWidget(name)

        form = QFormLayout()
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("Tüm sayfalar (ör. 1, 3-5)")
        form.addRow("&Sayfalar", self.pages)

        self.direction = QComboBox()
        self.direction.addItem("90° sağa", 90)
        self.direction.addItem("90° sola", -90)
        self.direction.addItem("180°", 180)
        form.addRow("&Dönüş", self.direction)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        buttons.addButton("Döndürülmüş PDF’yi kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
