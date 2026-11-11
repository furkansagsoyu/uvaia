"""Yerel video dönüştürme, kesme ve dışa aktarma araçları."""

from __future__ import annotations

import os
import re
import selectors
import subprocess
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from typing import BinaryIO

from imageio_ffmpeg import get_ffmpeg_exe

from job_progress import JobProgress
from output_files import save_new_file

VIDEO_CONTAINERS = {".mp4": "mp4", ".mkv": "matroska", ".mov": "mov", ".webm": "webm", ".avi": "avi"}
VIDEO_EXTENSIONS = tuple(VIDEO_CONTAINERS)
VIDEO_EXPORT_OPTIONS = {
    "MP4": (
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-f", "mp4",
    ),
    "WebM": (
        "-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "4", "-crf", "32", "-b:v", "0",
        "-c:a", "libopus", "-b:a", "128k", "-f", "webm",
    ),
}
INPUT_DURATION = re.compile(
    rb"(?m)^  Duration: ([0-9]+):([0-9]{2}):([0-9]{2})(?:\.([0-9]+))?,"
)
TIMESTAMP = re.compile(r"([0-9]{1,7}(?::[0-9]{1,2}){0,2})(?:[.,]([0-9]{1,3}))?")


def ffmpeg_command(
    source: Path,
    output: Path | str,
    options: tuple[str, ...],
    *,
    seek: str | None = None,
    loglevel: str = "error",
) -> list[str]:
    try:
        ffmpeg = get_ffmpeg_exe()
    except RuntimeError as error:
        raise ValueError("FFmpeg bulunamadı. Uvaia’nın bağımlılıklarını yeniden kur.") from error

    command = [
        ffmpeg,
        "-nostdin", "-hide_banner", "-loglevel", loglevel, "-y",
        "-protocol_whitelist", "file",
    ]
    if seek is not None:
        command.extend(("-ss", seek))
    command.extend(("-i", str(source.absolute()), *options, str(output)))
    return command


def run_ffmpeg(
    source: Path,
    output: Path | str,
    options: tuple[str, ...],
    *,
    seek: str | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    command = ffmpeg_command(source, output, options, seek=seek)
    return subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
    )


def run_video_process(
    command: list[str],
    progress: JobProgress,
    *,
    on_time: Callable[[int], None] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    progress.check_cancelled()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    pending = b""
    deadline = monotonic() + timeout if timeout is not None else None
    with subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as process, selectors.DefaultSelector() as selector:
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        try:
            while selector.get_map() or process.poll() is None:
                progress.check_cancelled()
                if deadline is not None and monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, timeout)
                for key, _ in selector.select(0.15):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffers[key.data].extend(chunk)
                    if key.data == "stdout" and on_time is not None:
                        lines = (pending + chunk).split(b"\n")
                        pending = lines.pop()
                        for line in lines:
                            name, _, value = line.strip().partition(b"=")
                            if name == b"out_time_us" and value.isdigit():
                                on_time(int(value))
            progress.check_cancelled()
        except BaseException:
            process.kill()
            raise

    return subprocess.CompletedProcess(
        command, process.returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"])
    )


def probe_video_duration(source: Path, progress: JobProgress) -> int | None:
    command = ffmpeg_command(
        source, "-", ("-t", "0", "-map", "0:V:0", "-c", "copy", "-f", "null"),
        loglevel="info",
    )
    try:
        probe = run_video_process(command, progress, timeout=8)
    except subprocess.TimeoutExpired:
        return None
    match = INPUT_DURATION.search(probe.stderr)
    if probe.returncode or match is None:
        return None

    hours, minutes, seconds = (int(value) for value in match.groups()[:3])
    fraction = int((match[4] or b"").ljust(6, b"0")[:6])
    microseconds = ((hours * 60 + minutes) * 60 + seconds) * 1_000_000 + fraction
    return microseconds or None


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


def save_encoded_video(
    source: Path,
    destination: Path,
    output_format: str,
    *,
    seek: str | None = None,
    duration_ms: int | None = None,
    speed: float = 1.0,
    progress: JobProgress | None = None,
) -> Path:
    limit = ("-t", format_timestamp(duration_ms)) if duration_ms is not None else ()
    total_us = None
    if progress is not None:
        total_us = duration_ms * 1000 if duration_ms is not None else probe_video_duration(
            source, progress
        )
        if total_us is not None:
            total_us = round(total_us / speed)
        progress.report(0, 100 if total_us else 0)

    def report_time(elapsed_us: int) -> None:
        if progress is not None and total_us:
            progress.report(min(99, elapsed_us * 100 // total_us), 100)
    video_filter = "pad=ceil(iw/2)*2:ceil(ih/2)*2"
    timing: tuple[str, ...] = ()
    if speed != 1:
        video_filter = f"{video_filter},settb=AVTB,setpts=PTS/{speed}"
        timing = ("-af", f"atempo={speed}", "-fps_mode", "vfr", "-enc_time_base:v", "filter")

    options = (
        *limit,
        "-map", "0:V:0", "-map", "0:a:0?",
        "-vf", video_filter, "-pix_fmt", "yuv420p",
        *timing,
        "-map_chapters", "-1", "-progress", "pipe:1",
        *VIDEO_EXPORT_OPTIONS[output_format],
    )

    def encode(stream: BinaryIO) -> None:
        output = Path(stream.name)
        if progress is None:
            process = run_ffmpeg(source, output, options, seek=seek)
        else:
            command = ffmpeg_command(source, output, options, seek=seek)
            process = run_video_process(command, progress, on_time=report_time)
        if process.returncode:
            if b"matches no streams" in process.stderr:
                raise ValueError("Dosyada video akışı bulunamadı.")
            raise ValueError(f"Video okunamadı veya {output_format} yazılamadı: {source.name}")
        if not re.search(rb"(?m)^frame=[ \t]*[1-9][0-9]*[ \t]*$", process.stdout):
            if duration_ms is not None:
                raise ValueError("Bu aralıkta video karesi yok. Daha erken bir başlangıç seç.")
            raise ValueError("Dosyada kaydedilebilecek video karesi yok.")
        if progress is not None:
            progress.check_cancelled()

    saved = save_new_file(destination, encode)
    if progress is not None:
        progress.report(100, 100)
    return saved


def trim_video(
    source: Path, start: int, end: int, *, progress: JobProgress | None = None
) -> Path:
    if start < 0 or end <= start:
        raise ValueError("Geçerli bir başlangıç ve bitiş zamanı seç.")

    seek = format_timestamp(start)
    finish = format_timestamp(end)
    destination = source.with_name(f"{source.stem}-kesit-{seek}s-{finish}s.mp4")
    return save_encoded_video(
        source, destination, "MP4", seek=seek, duration_ms=end - start, progress=progress
    )


def convert_video(
    source: Path, output_format: str, *, progress: JobProgress | None = None
) -> Path:
    if output_format not in VIDEO_EXPORT_OPTIONS:
        raise ValueError("Video biçimi olarak MP4 veya WebM seç.")
    destination = source.with_suffix(f".{output_format.lower()}")
    return save_encoded_video(source, destination, output_format, progress=progress)


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


def change_video_speed(
    source: Path, speed: float, *, progress: JobProgress | None = None
) -> Path:
    if not 0.5 <= speed <= 2.0:
        raise ValueError("Video hızı 0,50× ile 2,00× arasında olmalı.")
    speed = round(speed, 2)
    if speed == 1:
        raise ValueError("Hızı değiştirmek için 1,00× dışında bir değer seç.")

    destination = source.with_name(f"{source.stem}-hiz-{speed:.2f}x.mp4")
    return save_encoded_video(source, destination, "MP4", speed=speed, progress=progress)
