"""Kesme pencerelerine ortak medya oynatma ve zaman çizelgesi ekler."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget

from video_tools import format_timestamp, parse_clip_range


class MediaTimeline(QWidget):
    def __init__(self, source: Path, start: QLineEdit, end: QLineEdit, *, video: bool) -> None:
        super().__init__()
        self.start, self.end = start, end
        self.stop_at: int | None = None
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(QAudioOutput(self))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if video:
            picture = QVideoWidget()
            picture.setMinimumHeight(150)
            self.player.setVideoOutput(picture)
            layout.addWidget(picture)
        form = QFormLayout()
        self.cursor = self.slider(form, "Oynatma konumu")
        self.left = self.slider(form, "Başlangıç tutamacı")
        self.right = self.slider(form, "Bitiş tutamacı")
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.play = QPushButton("Oynat")
        self.play.clicked.connect(self.toggle)
        self.selection = QPushButton("Kesiti oynat")
        self.selection.clicked.connect(self.play_selection)
        actions.addWidget(self.play)
        actions.addWidget(self.selection)
        layout.addLayout(actions)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.cursor.sliderMoved.connect(self.player.setPosition)
        self.left.sliderMoved.connect(lambda value: self.set_boundary(True, value))
        self.right.sliderMoved.connect(lambda value: self.set_boundary(False, value))
        start.textChanged.connect(self.sync_bounds)
        end.textChanged.connect(self.sync_bounds)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(self.update_play)
        self.player.errorOccurred.connect(self.show_error)
        self.duration_changed(0)
        self.player.setSource(QUrl.fromLocalFile(str(source.absolute())))

    @staticmethod
    def slider(form: QFormLayout, label: str) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setAccessibleName(label)
        form.addRow(label, slider)
        return slider

    def duration_changed(self, duration: int) -> None:
        for slider in (self.cursor, self.left, self.right):
            slider.setRange(0, duration)
            slider.setEnabled(duration > 0)
        self.play.setEnabled(duration > 0)
        if duration and not self.end.text():
            self.end.setText(format_timestamp(duration))
        self.sync_bounds()

    def sync_bounds(self) -> None:
        try:
            start, end = parse_clip_range(self.start.text(), self.end.text())
        except ValueError:
            self.selection.setEnabled(False)
            return
        self.selection.setEnabled(self.player.duration() > 0)
        for slider, value in ((self.left, start), (self.right, end)):
            with QSignalBlocker(slider):
                slider.setValue(value)

    def set_boundary(self, left: bool, value: int) -> None:
        if left:
            value = min(value, max(0, self.right.value() - 1))
            self.start.setText(format_timestamp(value))
        else:
            value = max(value, self.left.value() + 1)
            self.end.setText(format_timestamp(value))
        self.player.setPosition(value)

    def position_changed(self, position: int) -> None:
        if not self.cursor.isSliderDown():
            self.cursor.setValue(position)
        if self.stop_at is not None and position >= self.stop_at:
            self.player.pause()
            self.stop_at = None

    def update_play(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play.setText("Duraklat" if state == QMediaPlayer.PlaybackState.PlayingState else "Oynat")

    def toggle(self) -> None:
        self.stop_at = None
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def play_selection(self) -> None:
        try:
            start, self.stop_at = parse_clip_range(self.start.text(), self.end.text())
        except ValueError:
            return
        self.player.setPosition(start)
        self.player.play()

    def show_error(self, *_args: object) -> None:
        self.status.setText("Bu dosya oynatılamadı. Kesim zamanlarını elle girebilirsin.")
