"""Shift çarkından seçilen dönüşümleri kaynak dosyaları koruyarak çalıştırır."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from audio_tools import convert_audio
from drag_wheel import shared_family
from image_conversion import convert_image
from job_progress import JobCancelled, JobProgress
from output_files import SavedOutputs
from pdf_render import render_pdf_pages
from pdf_text import extract_pdf_text
from pdf_tools import images_to_pdf
from video_tools import convert_video


def convert_drop_files(
    paths: tuple[Path, ...], output: str, progress: JobProgress
) -> Path | SavedOutputs:
    family = shared_family(paths)
    if family == "image" and output == "PDF":
        progress.check_cancelled()
        return images_to_pdf(list(paths))

    if family == "pdf" and len(paths) == 1 and output != "TXT":
        return render_pdf_pages(paths[0], "", output, progress=progress)

    saved: list[Path] = []
    failed: list[str] = []
    details: list[str] = []
    total = len(paths) * 100
    progress.report(0, total)
    for index, path in enumerate(paths):
        def report(done: int, count: int) -> None:
            progress.report(index * 100 + (done * 100 // count if count else 0), total)

        step = JobProgress(report, progress.is_cancelled)
        try:
            progress.check_cancelled()
            if family == "video" and output != "MP3":
                result = convert_video(path, output, progress=step)
            elif family in ("video", "audio"):
                result = convert_audio(path, output, progress=step)
            elif family == "pdf":
                result = extract_pdf_text(path, "") if output == "TXT" else render_pdf_pages(
                    path, "", output, progress=step
                )
            else:
                result = convert_image(path, output)
            if isinstance(result, SavedOutputs):
                saved.extend(result.paths)
                details.append(f"{path.name} — {result.message}")
                if progress.is_cancelled():
                    raise JobCancelled
            else:
                saved.append(result)
        except JobCancelled:
            if not saved:
                raise
            return SavedOutputs(tuple(saved), f"İşlem iptal edildi. {len(saved)} çıktı kaydedildi.")
        except (OSError, ValueError, Image.DecompressionBombError):
            if len(paths) == 1:
                raise
            failed.append(path.name)
        report(1, 1)

    if not saved:
        raise ValueError("Seçilen dosyalar dönüştürülemedi: " + ", ".join(failed))
    if len(paths) == 1 and len(saved) == 1 and not details:
        return saved[0]
    message = f"{len(saved)} çıktı kaydedildi."
    if failed:
        message += " Dönüştürülemeyen dosyalar: " + ", ".join(failed)
    if details:
        message += " " + " ".join(details)
    return SavedOutputs(tuple(saved), message)
