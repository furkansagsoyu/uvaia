"""Videodan yerel olarak ses ve görüntü çıkarır."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import BinaryIO

from imageio_ffmpeg import get_ffmpeg_exe

from output_files import save_new_file

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".webm", ".avi")
TIMESTAMP = re.compile(r"([0-9]{1,7}(?::[0-9]{1,2}){0,2})(?:[.,]([0-9]{1,3}))?")


def run_ffmpeg(
    source: Path,
    output: Path,
    options: tuple[str, ...],
    *,
    seek: str | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        ffmpeg = get_ffmpeg_exe()
    except RuntimeError as error:
        raise ValueError("FFmpeg bulunamadı. Uvaia’nın bağımlılıklarını yeniden kur.") from error

    command = [
        ffmpeg,
        "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-protocol_whitelist", "file",
    ]
    if seek is not None:
        command.extend(("-ss", seek))
    command.extend(("-i", str(source.absolute()), *options, str(output)))
    return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def extract_mp3(source: Path) -> Path:
    def encode(stream: BinaryIO) -> None:
        output = Path(stream.name)
        process = run_ffmpeg(
            source, output, ("-map", "0:a:0", "-c:a", "libmp3lame", "-q:a", "2", "-f", "mp3")
        )
        if process.returncode or output.stat().st_size == 0:
            if b"matches no streams" in process.stderr:
                raise ValueError("Videoda ses parçası bulunamadı.")
            raise ValueError(f"Videonun sesi okunamadı veya MP3 yazılamadı: {source.name}")

    return save_new_file(source.with_suffix(".mp3"), encode)


def parse_timestamp(value: str) -> str:
    """Kullanıcının girdiği zamanı FFmpeg için saniye ve milisaniyeye çevirir."""
    match = TIMESTAMP.fullmatch(value.strip())
    if match is None:
        raise ValueError("Zamanı saniye veya 00:12.500 biçiminde yaz.")

    parts = [int(part) for part in match[1].split(":")]
    if any(part >= 60 for part in parts[1:]):
        raise ValueError("Saat biçiminde son iki bölüm 0–59 arasında olmalı.")
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    fraction = (match[2] or "").ljust(3, "0")
    return f"{seconds}.{fraction}"


def extract_frame(source: Path, timestamp: str) -> Path:
    seek = parse_timestamp(timestamp)

    def encode(stream: BinaryIO) -> None:
        output = Path(stream.name)
        process = run_ffmpeg(
            source,
            output,
            ("-map", "0:V:0", "-frames:v", "1", "-c:v", "png", "-f", "image2", "-update", "1"),
            seek=seek,
        )
        if process.returncode:
            if b"matches no streams" in process.stderr:
                raise ValueError("Dosyada video akışı bulunamadı.")
            raise ValueError(f"Video karesi okunamadı veya PNG yazılamadı: {source.name}")
        if output.stat().st_size == 0:
            raise ValueError("Bu zamanda video karesi yok. Daha erken bir zaman seç.")

    destination = source.with_name(f"{source.stem}-kare-{seek}s.png")
    return save_new_file(destination, encode)
