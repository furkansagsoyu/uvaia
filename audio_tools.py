"""Yerel ses dosyalarını MP3, WAV veya FLAC biçiminde kaydeder."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from job_progress import JobProgress
from output_files import save_new_file
from video_tools import ffmpeg_command, probe_media_duration, run_ffmpeg, run_ffmpeg_process

AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aif", ".aiff")
AUDIO_EXPORT_OPTIONS = {
    "MP3": ("-c:a", "libmp3lame", "-q:a", "2", "-f", "mp3"),
    "WAV": ("-c:a", "pcm_s16le", "-f", "wav"),
    "FLAC": ("-c:a", "flac", "-f", "flac"),
}


def convert_audio(
    source: Path, output_format: str, *, progress: JobProgress | None = None
) -> Path:
    if output_format not in AUDIO_EXPORT_OPTIONS:
        raise ValueError("Ses biçimi olarak MP3, WAV veya FLAC seç.")

    total_us = None
    if progress is not None:
        total_us = probe_media_duration(source, progress, stream="0:a:0")
        progress.report(0, 100 if total_us else 0)

    def report_time(elapsed_us: int) -> None:
        if progress is not None and total_us:
            progress.report(min(99, elapsed_us * 100 // total_us), 100)

    def encode(stream: BinaryIO) -> None:
        output = Path(stream.name)
        options = (
            "-map", "0:a:0", "-abort_on", "empty_output", *AUDIO_EXPORT_OPTIONS[output_format]
        )
        if progress is None:
            process = run_ffmpeg(source, output, options)
        else:
            command = ffmpeg_command(source, output, ("-progress", "pipe:1", *options))
            process = run_ffmpeg_process(command, progress, on_time=report_time)
        if process.returncode or output.stat().st_size == 0:
            if b"matches no streams" in process.stderr:
                raise ValueError("Dosyada ses akışı bulunamadı.")
            raise ValueError(f"Ses okunamadı veya {output_format} yazılamadı: {source.name}")
        if progress is not None:
            progress.check_cancelled()

    destination = source.with_suffix(f".{output_format.lower()}")
    output = save_new_file(destination, encode)
    if progress is not None:
        progress.report(100, 100)
    return output
