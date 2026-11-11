"""Görsel ve PDF sayfalarındaki yazıyı yerel Tesseract ile tanır."""

from __future__ import annotations

import shutil
import subprocess
from contextlib import closing
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdfium2 import PdfDocument

from image_conversion import flatten_on_white, read_still_image
from output_files import save_new_file
from pdf_render import open_pdf_document, page_image, page_indices
from pdf_text import save_pdf_text

OCR_DPI = 300
OCR_LANGUAGES = ("tur", "eng")
OCR_TEXT = "Metin (.txt)"
OCR_SEARCHABLE_PDF = "Aranabilir PDF (.pdf)"
OCR_EXPORT_FORMATS = (OCR_TEXT, OCR_SEARCHABLE_PDF)
MAX_OCR_PIXELS = 32_000_000


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


def run_tesseract(
    image: Image.Image,
    tesseract: str,
    *,
    dpi: int | None = None,
    output: Literal["txt", "pdf"] = "txt",
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
        result = subprocess.run(command, input=data, capture_output=True, timeout=90)
    except subprocess.TimeoutExpired as error:
        raise ValueError("OCR zaman aşımına uğradı.") from error
    if result.returncode:
        raise ValueError("Tesseract görseli işleyemedi.")
    return result.stdout


def recognize_image(image: Image.Image, tesseract: str, *, dpi: int | None = None) -> str:
    return run_tesseract(image.convert("L"), tesseract, dpi=dpi).decode("utf-8", errors="replace")


def save_searchable_pdf(source: Path, selection: str, tesseract: str) -> Path:
    with closing(open_pdf_document(source)) as document, PdfWriter() as writer:
        for index in page_indices(document, selection):
            try:
                with page_image(document, index, scale=OCR_DPI / 72) as image:
                    data = run_tesseract(image, tesseract, dpi=OCR_DPI, output="pdf")
                with BytesIO(data) as stream, PdfReader(stream) as reader:
                    if len(reader.pages) != 1:
                        raise ValueError("Tesseract tek sayfalık PDF üretmedi.")
                    writer.add_page(reader.pages[0])
            except (PdfReadError, ValueError) as error:
                raise ValueError(f"{index + 1}. sayfa için OCR PDF’si oluşturulamadı. {error}") from error

        destination = source.with_name(f"{source.stem}-aranabilir.pdf")
        return save_new_file(destination, writer.write)


def ocr_pdf(source: Path, selection: str, output_format: str = OCR_TEXT) -> Path:
    if output_format not in OCR_EXPORT_FORMATS:
        raise ValueError("OCR çıktısı için metin veya aranabilir PDF seç.")
    tesseract = find_tesseract()
    if output_format == OCR_SEARCHABLE_PDF:
        return save_searchable_pdf(source, selection, tesseract)

    def read_page(document: PdfDocument, index: int) -> str:
        with page_image(document, index, scale=OCR_DPI / 72) as image:
            return recognize_image(image, tesseract, dpi=OCR_DPI)

    destination = source.with_name(f"{source.stem}-ocr.txt")
    return save_pdf_text(
        source, selection, destination, read_page,
        "Seçilen sayfalarda okunabilir yazı bulunamadı.",
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
