"""PDF bölümlerinin sayfalarını ve boyutunu seçtirir."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)


class PdfSplitDialog(QDialog):
    def __init__(self, filename: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("PDF’yi böl")
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

        self.group_size = QSpinBox()
        self.group_size.setRange(1, 9999)
        form.addRow("&Dosya başına sayfa", self.group_size)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        self.save = buttons.addButton("Böl ve kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
