"""Taranmış PDF sayfalarındaki yazıyı yerel Tesseract ile tanır."""

from __future__ import annotations

import shutil
import subprocess
from io import BytesIO
from pathlib import Path

from pypdfium2 import PdfDocument

from pdf_render import page_image
from pdf_text import save_pdf_text

OCR_DPI = 300
OCR_LANGUAGES = ("tur", "eng")


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


def ocr_pdf(source: Path, selection: str) -> Path:
    tesseract = find_tesseract()

    def read_page(document: PdfDocument, index: int) -> str:
        with page_image(document, index, scale=OCR_DPI / 72) as image:
            with BytesIO() as png:
                image.save(png, format="PNG", dpi=(OCR_DPI, OCR_DPI))
                data = png.getvalue()

        try:
            result = subprocess.run(
                [
                    tesseract, "stdin", "stdout", "-l", "+".join(OCR_LANGUAGES),
                    "--dpi", str(OCR_DPI),
                ],
                input=data,
                capture_output=True,
                timeout=90,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("OCR zaman aşımına uğradı.") from error
        if result.returncode:
            raise ValueError("Tesseract sayfa görüntüsünü işleyemedi.")
        return result.stdout.decode("utf-8", errors="replace")

    destination = source.with_name(f"{source.stem}-ocr.txt")
    return save_pdf_text(
        source, selection, destination, read_page,
        "Seçilen sayfalarda okunabilir yazı bulunamadı.",
    )
