"""PDF’nin metin katmanını sayfa sırasıyla UTF-8 olarak dışa aktarır."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import BinaryIO

from pypdfium2 import PdfiumError

from output_files import save_new_file
from pdf_render import open_pdf_document, page_indices


def extract_pdf_text(source: Path, selection: str) -> Path:
    def write_text(stream: BinaryIO) -> None:
        found = False
        with closing(open_pdf_document(source)) as document:
            for index in page_indices(document, selection):
                try:
                    with closing(document[index]) as page:
                        with closing(page.get_textpage()) as text_page:
                            text = text_page.get_text_bounded(errors="replace")
                except PdfiumError as error:
                    raise ValueError(f"{index + 1}. sayfanın metni okunamadı.") from error

                text = text.replace("\r\n", "\n").strip()
                if not text:
                    continue
                if found:
                    stream.write(b"\n")
                stream.write(f"Sayfa {index + 1}\n{text}\n".encode("utf-8"))
                found = True
        if not found:
            raise ValueError("Seçilen sayfalarda seçilebilir metin bulunamadı.")

    destination = source.with_name(f"{source.stem}-metin.txt")
    return save_new_file(destination, write_text)
