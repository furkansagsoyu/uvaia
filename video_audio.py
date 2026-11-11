"""Videonun ilk ses akışını yerel olarak MP3'e dönüştürür."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import BinaryIO

from imageio_ffmpeg import get_ffmpeg_exe

from output_files import save_new_file

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".webm", ".avi")


def extract_mp3(source: Path) -> Path:
    try:
        ffmpeg = get_ffmpeg_exe()
    except RuntimeError as error:
        raise ValueError("FFmpeg bulunamadı. Uvaia’nın bağımlılıklarını yeniden kur.") from error

    def encode(stream: BinaryIO) -> None:
        command = [
            ffmpeg,
            "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-protocol_whitelist", "file", "-i", str(source.absolute()),
            "-map", "0:a:0", "-c:a", "libmp3lame", "-q:a", "2",
            "-f", "mp3", str(stream.name),
        ]
        process = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if process.returncode:
            if b"matches no streams" in process.stderr:
                raise ValueError("Videoda ses parçası bulunamadı.")
            raise ValueError(f"Videonun sesi okunamadı veya MP3 yazılamadı: {source.name}")

    return save_new_file(source.with_suffix(".mp3"), encode)
