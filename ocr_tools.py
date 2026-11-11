"""Görsel ve PDF sayfalarındaki yazıyı yerel Tesseract ile tanır."""

from __future__ import annotations

import shutil
import subprocess
from contextlib import closing
from io import BytesIO
from pathlib import Path
from time import monotonic
from typing import BinaryIO, Literal

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdfium2 import PdfDocument

from image_conversion import flatten_on_white, read_still_image
from job_progress import JobCancelled, JobProgress, tracked_pages
from output_files import save_new_file
from pdf_render import open_pdf_document, page_image, page_indices
from pdf_text import save_pdf_text

OCR_DPI = 300
OCR_LANGUAGES = ("tur", "eng")
OCR_TEXT = "Metin (.txt)"
OCR_SEARCHABLE_PDF = "Aranabilir PDF (.pdf)"
OCR_EXPORT_FORMATS = (OCR_TEXT, OCR_SEARCHABLE_PDF)
MAX_OCR_PIXELS = 32_000_000
OCR_TIMEOUT = 90


def find_tesseract() -> str:
    executable = shutil.which("tesseract")
    if executable is None:
        raise ValueError("OCR için Tesseract kurulu olmalı. Kurulum komutu README’de.")

    try:
        languages = subprocess.run(
            [executable, "--list-langs"], capture_output=True, timeout=10
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Tesseract dil denetimi zaman aşımına uğradı.") from error
    installed = set(languages.stdout.decode("utf-8", errors="replace").splitlines())
    if languages.returncode or not set(OCR_LANGUAGES).issubset(installed):
        raise ValueError("OCR için Türkçe ve İngilizce Tesseract dil paketlerini kur.")
    return executable


def invoke_tesseract(
    command: list[str], data: bytes, progress: JobProgress | None
) -> subprocess.CompletedProcess[bytes]:
    if progress is None:
        return subprocess.run(command, input=data, capture_output=True, timeout=OCR_TIMEOUT)

    progress.check_cancelled()
    with subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as process:
        deadline = monotonic() + OCR_TIMEOUT
        pending: bytes | None = data
        try:
            while True:
                progress.check_cancelled()
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, OCR_TIMEOUT)
                try:
                    stdout, stderr = process.communicate(input=pending, timeout=min(0.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    # communicate yarım kalan girdi ve çıktıyı kendi tamponunda tutar.
                    pending = None
        except (JobCancelled, subprocess.TimeoutExpired):
            process.kill()
            process.communicate()
            raise

    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def run_tesseract(
    image: Image.Image,
    tesseract: str,
    *,
    dpi: int | None = None,
    output: Literal["txt", "pdf"] = "txt",
    progress: JobProgress | None = None,
) -> bytes:
    if image.width * image.height > MAX_OCR_PIXELS:
        raise ValueError("Görsel OCR boyut sınırını aşıyor.")

    command = [tesseract, "stdin", "stdout", "-l", "+".join(OCR_LANGUAGES)]
    if dpi is not None:
        command.extend(("--dpi", str(dpi)))
    if output == "pdf":
        command.append("pdf")
    png_options = {"dpi": (dpi, dpi)} if dpi is not None else {}
    with BytesIO() as png:
        image.save(png, format="PNG", **png_options)
        data = png.getvalue()

    try:
        result = invoke_tesseract(command, data, progress)
    except subprocess.TimeoutExpired as error:
        raise ValueError("OCR zaman aşımına uğradı.") from error
    if result.returncode:
        raise ValueError("Tesseract görseli işleyemedi.")
    return result.stdout


def recognize_image(
    image: Image.Image,
    tesseract: str,
    *,
    dpi: int | None = None,
    progress: JobProgress | None = None,
) -> str:
    data = run_tesseract(image.convert("L"), tesseract, dpi=dpi, progress=progress)
    return data.decode("utf-8", errors="replace")


def save_searchable_pdf(
    source: Path, selection: str, tesseract: str, progress: JobProgress | None
) -> Path:
    with closing(open_pdf_document(source)) as document, PdfWriter() as writer:
        pages = page_indices(document, selection)
        for index in tracked_pages(pages, progress):
            try:
                with page_image(document, index, scale=OCR_DPI / 72) as image:
                    data = run_tesseract(
                        image, tesseract, dpi=OCR_DPI, output="pdf", progress=progress
                    )
                with BytesIO(data) as stream, PdfReader(stream) as reader:
                    if len(reader.pages) != 1:
                        raise ValueError("Tesseract tek sayfalık PDF üretmedi.")
                    writer.add_page(reader.pages[0])
            except (PdfReadError, ValueError) as error:
                raise ValueError(f"{index + 1}. sayfa için OCR PDF’si oluşturulamadı. {error}") from error

        def write_pdf(stream: BinaryIO) -> None:
            writer.write(stream)
            if progress is not None:
                progress.check_cancelled()

        destination = source.with_name(f"{source.stem}-aranabilir.pdf")
        return save_new_file(destination, write_pdf)


def ocr_pdf(
    source: Path,
    selection: str,
    output_format: str = OCR_TEXT,
    *,
    progress: JobProgress | None = None,
) -> Path:
    if output_format not in OCR_EXPORT_FORMATS:
        raise ValueError("OCR çıktısı için metin veya aranabilir PDF seç.")
    if progress is not None:
        progress.check_cancelled()
    tesseract = find_tesseract()
    if output_format == OCR_SEARCHABLE_PDF:
        return save_searchable_pdf(source, selection, tesseract, progress)

    def read_page(document: PdfDocument, index: int) -> str:
        with page_image(document, index, scale=OCR_DPI / 72) as image:
            return recognize_image(image, tesseract, dpi=OCR_DPI, progress=progress)

    destination = source.with_name(f"{source.stem}-ocr.txt")
    return save_pdf_text(
        source, selection, destination, read_page,
        "Seçilen sayfalarda okunabilir yazı bulunamadı.",
        progress=progress,
    )


def ocr_image(source: Path) -> Path:
    tesseract = find_tesseract()
    image, _ = read_still_image(source)
    text = recognize_image(flatten_on_white(image), tesseract).replace("\r\n", "\n").strip()
    if not text:
        raise ValueError("Görselde okunabilir yazı bulunamadı.")

    destination = source.with_name(f"{source.stem}-ocr.txt")
    data = f"{text}\n".encode("utf-8")
    return save_new_file(destination, lambda stream: stream.write(data))
