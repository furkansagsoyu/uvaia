"""Video kesitlerini, kareleri, sesi ve sessiz kopyaları dışa aktarır."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import BinaryIO

from imageio_ffmpeg import get_ffmpeg_exe

from output_files import save_new_file

VIDEO_CONTAINERS = {".mp4": "mp4", ".mkv": "matroska", ".mov": "mov", ".webm": "webm", ".avi": "avi"}
VIDEO_EXTENSIONS = tuple(VIDEO_CONTAINERS)
TIMESTAMP = re.compile(r"([0-9]{1,7}(?::[0-9]{1,2}){0,2})(?:[.,]([0-9]{1,3}))?")


def run_ffmpeg(
    source: Path,
    output: Path | str,
    options: tuple[str, ...],
    *,
    seek: str | None = None,
    timeout: float | None = None,
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
    return subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
    )


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


def timestamp_milliseconds(value: str) -> int:
    """Kullanıcının girdiği zamanı milisaniyeye çevirir."""
    match = TIMESTAMP.fullmatch(value.strip())
    if match is None:
        raise ValueError("Zamanı saniye veya 00:12.500 biçiminde yaz.")

    parts = [int(part) for part in match[1].split(":")]
    if any(part >= 60 for part in parts[1:]):
        raise ValueError("Saat biçiminde son iki bölüm 0–59 arasında olmalı.")
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    fraction = int((match[2] or "").ljust(3, "0"))
    return seconds * 1000 + fraction


def format_timestamp(milliseconds: int) -> str:
    seconds, fraction = divmod(milliseconds, 1000)
    return f"{seconds}.{fraction:03d}"


def parse_clip_range(start: str, end: str) -> tuple[int, int]:
    begin = timestamp_milliseconds(start)
    finish = timestamp_milliseconds(end)
    if finish <= begin:
        raise ValueError("Bitiş zamanı başlangıçtan sonra olmalı.")
    return begin, finish


def preview_frame(source: Path, timestamp: str) -> bytes:
    seek = format_timestamp(timestamp_milliseconds(timestamp))
    try:
        process = run_ffmpeg(
            source,
            "pipe:1",
            (
                "-map", "0:V:0", "-frames:v", "1",
                "-vf", "scale=320:180:force_original_aspect_ratio=decrease",
                "-c:v", "png", "-f", "image2pipe",
            ),
            seek=seek,
            timeout=15,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Önizleme zaman aşımına uğradı.") from error
    if process.returncode:
        raise ValueError("Videodan önizleme alınamadı.")
    if not process.stdout:
        raise ValueError("Bu zamanda video karesi yok. Daha erken bir zaman seç.")
    return process.stdout


def extract_frame(source: Path, timestamp: str) -> Path:
    seek = format_timestamp(timestamp_milliseconds(timestamp))

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


def trim_video(source: Path, start: int, end: int) -> Path:
    if start < 0 or end <= start:
        raise ValueError("Geçerli bir başlangıç ve bitiş zamanı seç.")

    seek = format_timestamp(start)
    duration = format_timestamp(end - start)
    options = (
        "-t", duration,
        "-map", "0:V:0", "-map", "0:a:0?",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-map_chapters", "-1", "-movflags", "+faststart",
        "-progress", "pipe:1", "-f", "mp4",
    )

    def encode(stream: BinaryIO) -> None:
        output = Path(stream.name)
        process = run_ffmpeg(source, output, options, seek=seek)
        if process.returncode:
            if b"matches no streams" in process.stderr:
                raise ValueError("Dosyada video akışı bulunamadı.")
            raise ValueError(f"Video okunamadı veya MP4 yazılamadı: {source.name}")
        if not re.search(rb"(?m)^frame=[ 	]*[1-9][0-9]*[ 	]*$", process.stdout):
            raise ValueError("Bu aralıkta video karesi yok. Daha erken bir başlangıç seç.")

    finish = format_timestamp(end)
    destination = source.with_name(f"{source.stem}-kesit-{seek}s-{finish}s.mp4")
    return save_new_file(destination, encode)


def mute_video(source: Path) -> Path:
    """Video akışlarını yeniden kodlamadan sessiz bir kopya yazar."""
    extension = source.suffix.lower()
    container = VIDEO_CONTAINERS.get(extension)
    if container is None:
        raise ValueError("Sessiz kopya için MP4, MKV, MOV, WebM veya AVI seç.")

    def encode(stream: BinaryIO) -> None:
        output = Path(stream.name)
        process = run_ffmpeg(
            source,
            output,
            ("-map", "0:V", "-map", "0:s?", "-map", "0:t?", "-c", "copy", "-an", "-f", container),
        )
        if process.returncode or output.stat().st_size == 0:
            if b"matches no streams" in process.stderr:
                raise ValueError("Dosyada video akışı bulunamadı.")
            raise ValueError(f"Sessiz video kopyası kaydedilemedi: {source.name}")

    destination = source.with_name(f"{source.stem}-sessiz{extension}")
    return save_new_file(destination, encode)
