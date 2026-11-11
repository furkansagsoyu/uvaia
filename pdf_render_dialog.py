"""PDF görsel dışa aktarımının biçimini ve sayfalarını seçtirir."""

from __future__ import annotations

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

from pdf_render import DPI


class PdfRenderDialog(QDialog):
    def __init__(self, filename: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("PDF’yi görsele dönüştür")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        name = QLabel(filename)
        name.setWordWrap(True)
        layout.addWidget(name)

        form = QFormLayout()
        self.output_format = QComboBox()
        self.output_format.addItems(("PNG", "JPG"))
        form.addRow("&Çıktı biçimi", self.output_format)

        self.pages = QLineEdit()
        self.pages.setPlaceholderText("Tüm sayfalar (ör. 1, 3-5)")
        form.addRow("&Sayfalar", self.pages)
        layout.addLayout(form)

        hint = QLabel(f"Her sayfa {DPI} DPI ile ayrı bir görsele kaydedilir.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox()
        buttons.addButton("Görselleri kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
