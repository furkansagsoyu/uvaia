"""PDF dışa aktarımının biçimini ve sayfalarını seçtirir."""

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


class PdfExportDialog(QDialog):
    def __init__(
        self,
        filename: str,
        parent: QWidget,
        *,
        title: str,
        formats: tuple[str, ...],
        hint: str,
        save_label: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        name = QLabel(filename)
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        layout.addWidget(name)

        form = QFormLayout()
        self.output_format = QComboBox()
        self.output_format.addItems(formats)
        form.addRow("&Çıktı biçimi", self.output_format)

        self.pages = QLineEdit()
        self.pages.setPlaceholderText("Tüm sayfalar (ör. 1, 3-5)")
        form.addRow("&Sayfalar", self.pages)
        layout.addLayout(form)

        description = QLabel(hint)
        description.setWordWrap(True)
        layout.addWidget(description)

        buttons = QDialogButtonBox()
        buttons.addButton(save_label, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
