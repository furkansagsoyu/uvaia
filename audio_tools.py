"""Yerel ses dosyalarını dönüştürür ve zaman aralığına göre keser."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from job_progress import JobProgress
from output_files import save_new_file
from video_tools import (
    ffmpeg_command, format_timestamp, probe_media_duration, run_ffmpeg, run_ffmpeg_process,
)

AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aif", ".aiff", ".wma")
AUDIO_EXPORT_OPTIONS = {
    "MP3": ("-c:a", "libmp3lame", "-q:a", "2", "-f", "mp3"),
    "WAV": ("-c:a", "pcm_s16le", "-f", "wav"),
    "FLAC": ("-c:a", "flac", "-f", "flac"),
    "M4A": ("-c:a", "aac", "-b:a", "192k", "-f", "ipod"),
    "OGG": ("-c:a", "libvorbis", "-q:a", "5", "-f", "ogg"),
    "Opus": ("-c:a", "libopus", "-b:a", "128k", "-f", "opus"),
    "AIFF": ("-c:a", "pcm_s16be", "-f", "aiff"),
    "WMA": ("-c:a", "wmav2", "-b:a", "192k", "-f", "asf"),
}


def save_audio(
    source: Path,
    destination: Path,
    output_format: str,
    *,
    interval: tuple[int, int] | None = None,
    audio_options: tuple[str, ...] = (),
    progress: JobProgress | None = None,
) -> Path:
    if output_format not in AUDIO_EXPORT_OPTIONS:
        raise ValueError("Geçerli bir ses biçimi seç.")

    seek = None
    limit: tuple[str, ...] = ()
    total_us = None
    if interval is not None:
        start, end = interval
        if start < 0 or end <= start:
            raise ValueError("Geçerli bir başlangıç ve bitiş zamanı seç.")
        seek = format_timestamp(start)
        limit = ("-t", format_timestamp(end - start))
        total_us = (end - start) * 1000

    if progress is not None:
        if total_us is None:
            total_us = probe_media_duration(source, progress, stream="0:a:0")
        progress.report(0, 100 if total_us else 0)

    def report_time(elapsed_us: int) -> None:
        if progress is not None and total_us:
            progress.report(min(99, elapsed_us * 100 // total_us), 100)

    def encode(stream: BinaryIO) -> None:
        output = Path(stream.name)
        options = (
            "-map", "0:a:0", "-abort_on", "empty_output", *limit, *audio_options, *AUDIO_EXPORT_OPTIONS[output_format]
        )
        if progress is None:
            process = run_ffmpeg(source, output, options, seek=seek)
        else:
            command = ffmpeg_command(
                source, output, ("-progress", "pipe:1", *options), seek=seek
            )
            process = run_ffmpeg_process(command, progress, on_time=report_time)
        if process.returncode or output.stat().st_size == 0:
            if b"matches no streams" in process.stderr:
                raise ValueError("Dosyada ses akışı bulunamadı.")
            if interval is not None and b"empty" in process.stderr.lower():
                raise ValueError("Bu aralıkta kaydedilebilecek ses bulunamadı.")
            raise ValueError(f"Ses okunamadı veya {output_format} yazılamadı: {source.name}")
        if progress is not None:
            progress.check_cancelled()

    output = save_new_file(destination, encode)
    if progress is not None:
        progress.report(100, 100)
    return output


def convert_audio(
    source: Path, output_format: str, *, progress: JobProgress | None = None
) -> Path:
    destination = source.with_suffix(f".{output_format.lower()}")
    return save_audio(source, destination, output_format, progress=progress)


def trim_audio(
    source: Path,
    interval: tuple[int, int],
    output_format: str,
    *,
    progress: JobProgress | None = None,
) -> Path:
    start, end = map(format_timestamp, interval)
    destination = source.with_name(
        f"{source.stem}-kesit-{start}s-{end}s.{output_format.lower()}"
    )
    return save_audio(
        source, destination, output_format, interval=interval, progress=progress
    )


def edit_audio(
    source: Path, *, channels: int | None = None, progress: JobProgress | None = None
) -> Path:
    if channels is None:
        suffix = "dengeli"
        options = ("-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000")
    else:
        suffix = "mono" if channels == 1 else "stereo"
        options = ("-ac", str(channels))
    return save_audio(
        source, source.with_name(f"{source.stem}-{suffix}.wav"), "WAV",
        audio_options=options, progress=progress,
    )
