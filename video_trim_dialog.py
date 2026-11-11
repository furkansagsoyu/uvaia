"""Video kesitinin başlangıç ve bitiş zamanlarını seçtirir."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from video_tools import format_timestamp, parse_clip_range


class VideoTrimDialog(QDialog):
    def __init__(self, filename: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Videoyu kes")
        self.setMinimumWidth(360)
        self.interval: tuple[int, int] | None = None

        layout = QVBoxLayout(self)
        name = QLabel(filename)
        name.setWordWrap(True)
        layout.addWidget(name)
        layout.addWidget(QLabel("Saniye veya dakika:saniye gir. Örneğin 12,5 ya da 00:12.500."))

        form = QFormLayout()
        self.start = QLineEdit("0")
        self.end = QLineEdit()
        self.end.setPlaceholderText("Ör. 15")
        form.addRow("&Başlangıç", self.start)
        form.addRow("B&itiş", self.end)
        layout.addLayout(form)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        buttons = QDialogButtonBox()
        self.save = buttons.addButton("Kesiti kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.start.textChanged.connect(self.update_interval)
        self.end.textChanged.connect(self.update_interval)
        self.end.setFocus()
        self.update_interval()

    def update_interval(self) -> None:
        self.interval = None
        if not self.start.text().strip() or not self.end.text().strip():
            self.hint.setText("Başlangıç ve bitiş zamanını gir.")
        else:
            try:
                self.interval = parse_clip_range(self.start.text(), self.end.text())
            except ValueError as error:
                self.hint.setText(str(error))
            else:
                start, end = self.interval
                duration = format_timestamp(end - start).replace(".", ",")
                self.hint.setText(f"Kesit süresi: {duration} saniye")
        self.save.setEnabled(self.interval is not None)
