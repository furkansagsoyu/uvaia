"""Seçilen medya dosyalarını ortak biçimde ve verilen sırada birleştirir."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO

from uvaia_app.core.job_progress import JobProgress, tracked_items
from uvaia_app.core.output_files import save_new_file
from uvaia_app.core.video_tools import ffmpeg_command, format_timestamp, probe_media_duration, run_ffmpeg_process


def join_media(sources: list[Path], *, video: bool, progress: JobProgress) -> Path:
    if len(sources) < 2:
        raise ValueError("En az iki dosya seç.")
    suffix = ".mp4" if video else ".wav"
    destination = sources[0].with_name(f"{sources[0].stem}-birlesik{suffix}")
    with TemporaryDirectory(prefix="uvaia-birlestir-") as directory:
        root = Path(directory)
        segments: list[Path] = []
        for source in tracked_items(sources, progress):
            segment = root / f"parca-{len(segments):04d}{suffix}"
            if video:
                visual = root / f"goruntu-{len(segments):04d}.mp4"
                render = ffmpeg_command(source, visual, (
                    "-map", "0:V:0", "-an", "-vf",
                    "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                    "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
                    "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-f", "mp4",
                ))
                if run_ffmpeg_process(render, progress).returncode:
                    raise ValueError(f"Görüntü hazırlanamadı: {source.name}")
                duration = probe_media_duration(visual, progress)
                if not duration:
                    raise ValueError(f"Video süresi okunamadı: {source.name}")
                probe = ffmpeg_command(source, "-", ("-t", "0", "-map", "0:a:0", "-f", "null"))
                audio = run_ffmpeg_process(probe, progress)
                if audio.returncode and b"matches no streams" not in audio.stderr:
                    raise ValueError(f"Ses akışı okunamadı: {source.name}")
                if audio.returncode:
                    sound = ("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "2:a:0")
                else:
                    sound = ("-map", "0:a:0", "-af", "apad")
                options = (
                    "-i", str(visual), *sound, "-map", "1:v:0", "-c:v", "copy",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2",
                    "-t", format_timestamp(round(duration / 1000)), "-f", "mp4",
                )
            else:
                options = ("-map", "0:a:0", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "-f", "wav")
            command = ffmpeg_command(source, segment, options)
            result = run_ffmpeg_process(command, progress)
            if result.returncode or not segment.is_file() or not segment.stat().st_size:
                raise ValueError(f"Dosya birleştirmeye hazırlanamadı: {source.name}")
            segments.append(segment)

        listing = root / "parcalar.txt"
        listing.write_text("".join(f"file '{segment.name}'\n" for segment in segments), encoding="ascii")
        def write(stream: BinaryIO) -> None:
            command = ffmpeg_command(listing, Path(stream.name), (
                "-c", "copy", "-f", "mp4" if video else "wav",
            ))
            input_index = command.index("-i")
            command[input_index:input_index] = ["-f", "concat", "-safe", "1"]
            result = run_ffmpeg_process(command, progress)
            if result.returncode or not Path(stream.name).stat().st_size:
                raise ValueError("Birleştirilen dosya kaydedilemedi.")
            progress.check_cancelled()

        return save_new_file(destination, write)
