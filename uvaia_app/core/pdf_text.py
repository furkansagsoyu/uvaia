"""PDF’nin metin katmanını sayfa sırasıyla UTF-8 olarak dışa aktarır."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import BinaryIO

from pypdfium2 import PdfDocument, PdfiumError

from uvaia_app.core.job_progress import JobProgress, tracked_items
from uvaia_app.core.output_files import save_new_file
from uvaia_app.core.pdf_render import open_pdf_document, page_indices


def save_pdf_text(
    source: Path,
    selection: str,
    destination: Path,
    read_page: Callable[[PdfDocument, int], str],
    empty_message: str,
    *,
    progress: JobProgress | None = None,
) -> Path:
    def write_text(stream: BinaryIO) -> None:
        found = False
        with closing(open_pdf_document(source)) as document:
            pages = page_indices(document, selection)
            for index in tracked_items(pages, progress):
                try:
                    text = read_page(document, index)
                except (PdfiumError, ValueError) as error:
                    raise ValueError(f"{index + 1}. sayfanın metni okunamadı. {error}") from error

                text = text.replace("\r\n", "\n").strip()
                if not text:
                    continue
                if found:
                    stream.write(b"\n")
                stream.write(f"Sayfa {index + 1}\n{text}\n".encode("utf-8"))
                found = True
        if not found:
            raise ValueError(empty_message)

    return save_new_file(destination, write_text)


def read_text_layer(document: PdfDocument, index: int) -> str:
    with closing(document[index]) as page:
        with closing(page.get_textpage()) as text_page:
            return text_page.get_text_bounded(errors="replace")


def extract_pdf_text(source: Path, selection: str) -> Path:
    destination = source.with_name(f"{source.stem}-metin.txt")
    return save_pdf_text(
        source, selection, destination, read_text_layer,
        "Seçilen sayfalarda seçilebilir metin bulunamadı.",
    )
