"""PDF sayfalarını yerel olarak PNG veya JPG dosyalarına dönüştürür."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from math import ceil, isfinite
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from image_conversion import FORMATS
from output_files import SavedOutputs, save_new_file
from pdf_tools import parse_pages

DPI = 144
SCALE = DPI / 72
MAX_PAGE_PIXELS = 32_000_000


def open_pdf_document(source: Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(source)
    except (pdfium.PdfiumError, OSError) as error:
        raise ValueError(f"PDF açılamadı: {source.name}") from error


def page_indices(document: pdfium.PdfDocument, selection: str) -> Sequence[int]:
    page_count = len(document)
    if page_count == 0:
        raise ValueError("PDF’de işlenecek sayfa yok.")
    return parse_pages(selection, page_count) if selection.strip() else range(page_count)


@contextmanager
def page_image(document: pdfium.PdfDocument, index: int) -> Iterator[Image.Image]:
    """Görseli kullanan işlem bitene kadar PDFium bitmap’ini açık tutar."""
    try:
        with closing(document[index]) as page:
            width, height = page.get_size()
            if (
                not (isfinite(width) and isfinite(height) and width > 0 and height > 0)
                or ceil(width * SCALE) * ceil(height * SCALE) > MAX_PAGE_PIXELS
            ):
                raise ValueError("Sayfa görüntüleme boyutu sınırını aşıyor.")
            with closing(page.render(scale=SCALE, rev_byteorder=True)) as bitmap:
                yield bitmap.to_pil()
    except pdfium.PdfiumError as error:
        raise ValueError(f"{index + 1}. sayfanın görüntüsü oluşturulamadı.") from error


def render_pdf_pages(source: Path, selection: str, output_format: str) -> Path | SavedOutputs:
    if output_format not in ("PNG", "JPG"):
        raise ValueError("PNG veya JPG biçimini seç.")

    with closing(open_pdf_document(source)) as document:
        pages = page_indices(document, selection)
        pillow_format = "JPEG" if output_format == "JPG" else output_format
        saved: list[Path] = []
        for index in pages:
            try:
                with page_image(document, index) as image:
                    if pillow_format == "JPEG" and image.mode != "RGB":
                        image = image.convert("RGB")
                    filename = f"{source.stem}-sayfa-{index + 1}{FORMATS[output_format]}"
                    destination = source.with_name(filename)
                    output = save_new_file(
                        destination,
                        lambda stream: image.save(stream, format=pillow_format, dpi=(DPI, DPI)),
                    )
                saved.append(output)
            except (OSError, ValueError) as error:
                detail = f"{index + 1}. sayfa dışa aktarılamadı."
                if isinstance(error, ValueError):
                    detail = f"{detail} {error}"
                if saved:
                    message = f"İşlem tamamlanamadı: {len(saved)} sayfa kaydedildi. {detail}"
                    return SavedOutputs(tuple(saved), message)
                raise ValueError(detail) from error

    if len(saved) == 1:
        return saved[0]
    return SavedOutputs(
        tuple(saved), f"{len(saved)} PDF sayfası {output_format} olarak kaydedildi."
    )
