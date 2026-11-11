"""Dosya seçimi ve sıralama penceresi."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FileOrderDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        hint: str,
        add_label: str,
        save_label: str,
        file_filter: str,
        minimum: int,
        initial: tuple[Path, ...] = (),
    ) -> None:
        super().__init__(parent)
        self.file_filter = file_filter
        self.minimum = minimum
        self.setWindowTitle(title)
        self.resize(490, 320)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(hint))
        self.files = QListWidget()
        self.files.setAccessibleName("Dosya sırası")
        layout.addWidget(self.files)

        actions = QHBoxLayout()
        add = QPushButton(add_label)
        add.clicked.connect(self.add_files)
        actions.addWidget(add)
        self.up = QPushButton("Yukarı")
        self.up.clicked.connect(lambda: self.move_file(-1))
        actions.addWidget(self.up)
        self.down = QPushButton("Aşağı")
        self.down.clicked.connect(lambda: self.move_file(1))
        actions.addWidget(self.down)
        self.remove = QPushButton("Kaldır")
        self.remove.clicked.connect(self.remove_file)
        actions.addWidget(self.remove)
        layout.addLayout(actions)

        buttons = QDialogButtonBox()
        self.save = buttons.addButton(save_label, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("İptal", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.files.currentRowChanged.connect(self.update_actions)
        self.add_paths(initial)

    def paths(self) -> list[Path]:
        return [
            Path(self.files.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(self.files.count())
        ]

    def add_files(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Eklenecek dosyaları seç", filter=self.file_filter
        )
        self.add_paths(tuple(Path(filename) for filename in filenames))

    def add_paths(self, paths: tuple[Path, ...]) -> None:
        current = set(self.paths())
        for path in paths:
            if path in current:
                continue
            current.add(path)
            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.files.addItem(item)
        if self.files.currentRow() < 0:
            self.files.setCurrentRow(0)
        self.update_actions()

    def move_file(self, offset: int) -> None:
        row = self.files.currentRow()
        destination = row + offset
        if row >= 0 and 0 <= destination < self.files.count():
            self.files.insertItem(destination, self.files.takeItem(row))
            self.files.setCurrentRow(destination)

    def remove_file(self) -> None:
        row = self.files.currentRow()
        if row >= 0:
            self.files.takeItem(row)
            self.update_actions()

    def update_actions(self) -> None:
        row = self.files.currentRow()
        count = self.files.count()
        self.up.setEnabled(row > 0)
        self.down.setEnabled(0 <= row < count - 1)
        self.remove.setEnabled(row >= 0)
        self.save.setEnabled(count >= self.minimum)
