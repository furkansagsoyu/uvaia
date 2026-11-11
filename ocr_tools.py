"""Görsel ve PDF sayfalarındaki yazıyı yerel Tesseract ile tanır."""

from __future__ import annotations

import shutil
import subprocess
from io import BytesIO
from pathlib import Path

from PIL import Image
from pypdfium2 import PdfDocument

from image_conversion import flatten_on_white, read_still_image
from output_files import save_new_file
from pdf_render import page_image
from pdf_text import save_pdf_text

OCR_DPI = 300
OCR_LANGUAGES = ("tur", "eng")
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


def recognize_image(image: Image.Image, tesseract: str, *, dpi: int | None = None) -> str:
    if image.width * image.height > MAX_OCR_PIXELS:
        raise ValueError("Görsel OCR boyut sınırını aşıyor.")

    command = [tesseract, "stdin", "stdout", "-l", "+".join(OCR_LANGUAGES)]
    if dpi is not None:
        command.extend(("--dpi", str(dpi)))
    with BytesIO() as png:
        image.convert("L").save(png, format="PNG")
        data = png.getvalue()

    try:
        result = subprocess.run(command, input=data, capture_output=True, timeout=90)
    except subprocess.TimeoutExpired as error:
        raise ValueError("OCR zaman aşımına uğradı.") from error
    if result.returncode:
        raise ValueError("Tesseract görseli işleyemedi.")
    return result.stdout.decode("utf-8", errors="replace")


def ocr_pdf(source: Path, selection: str) -> Path:
    tesseract = find_tesseract()

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
