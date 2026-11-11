"""PDF birleştirme ve sayfa çıkarma işlemleri."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from output_files import save_new_file

PAGE_RANGE = re.compile(r"([0-9]{1,10})(?:\s*[-–]\s*([0-9]{1,10}))?")


@contextmanager
def read_pdf(source: Path) -> Iterator[PdfReader]:
    try:
        with PdfReader(source) as reader:
            if reader.is_encrypted:
                raise ValueError(f"Şifreli PDF açılamıyor: {source.name}")
            yield reader
    except (PdfReadError, OSError) as error:
        raise ValueError(f"PDF okunamadı: {source.name}") from error


def merge_pdfs(sources: list[Path]) -> Path:
    if len(sources) < 2:
        raise ValueError("En az iki PDF seç.")

    with PdfWriter() as writer:
        for index, source in enumerate(sources, start=1):
            with read_pdf(source) as reader:
                if reader.get_fields():
                    reader.add_form_topname(f"Belge{index}")
                writer.append(reader)

        first = sources[0]
        destination = first.with_name(f"{first.stem}-birlesik.pdf")
        return save_new_file(destination, writer.write)


def parse_pages(selection: str, page_count: int) -> list[int]:
    """Kullanıcının girdiği bir tabanlı sayfaları giriş sırasıyla çözer."""
    pages: list[int] = []
    seen: set[int] = set()
    for entry in selection.split(","):
        match = PAGE_RANGE.fullmatch(entry.strip())
        if match is None:
            raise ValueError("Sayfa seçimini 1, 3-5 biçiminde yaz.")

        start = int(match[1])
        end = int(match[2]) if match[2] is not None else start
        if start < 1 or start > end or end > page_count:
            raise ValueError(
                f"Geçersiz sayfa seçimi: {entry.strip()}. PDF’de {page_count} sayfa var."
            )
        for page in range(start - 1, end):
            if page in seen:
                raise ValueError(f"{page + 1}. sayfa birden fazla kez seçilmiş.")
            seen.add(page)
            pages.append(page)
    return pages


def extract_pages(source: Path, selection: str) -> Path:
    with PdfWriter() as writer:
        with read_pdf(source) as reader:
            pages = parse_pages(selection, len(reader.pages))
            writer.append(reader, pages=pages)

        destination = source.with_name(f"{source.stem}-sayfalar.pdf")
        return save_new_file(destination, writer.write)
