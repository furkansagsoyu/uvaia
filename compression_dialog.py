"""Sıkıştırılmış görsel kopyası için biçim ve kalite seçtirir."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class CompressionDialog(QDialog):
    def __init__(self, filename: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Görseli sıkıştır")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        name = QLabel(filename)
        name.setWordWrap(True)
        layout.addWidget(name)

        form = QFormLayout()
        self.output_format = QComboBox()
        self.output_format.addItems(("WebP", "JPG"))
        form.addRow("&Çıktı biçimi", self.output_format)

        self.quality = QSpinBox()
        self.quality.setRange(1, 95)
        self.quality.setValue(75)
        form.addRow("&Kalite", self.quality)
        layout.addLayout(form)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.output_format.currentTextChanged.connect(self.update_hint)
        self.update_hint(self.output_format.currentText())

        buttons = QDialogButtonBox()
        buttons.addButton("Sıkıştırılmış kopyayı kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def update_hint(self, output_format: str) -> None:
        transparency = (
            "JPG’de şeffaf alanlar beyaz olur."
            if output_format == "JPG"
            else "WebP şeffaflığı korur."
        )
        self.hint.setText(f"Düşük kalite genellikle daha az yer kaplar. {transparency}")
