"""PDF birleştirme, sayfa düzenleme ve görsel dışa aktarma işlemleri."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from image_conversion import flatten_on_white, read_still_image
from job_progress import JobCancelled, JobProgress, tracked_items
from output_files import SavedOutputs, save_new_file

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


def images_to_pdf(sources: list[Path]) -> Path:
    if not sources:
        raise ValueError("En az bir görsel seç.")

    with PdfWriter() as writer:
        for source in sources:
            try:
                image, _ = read_still_image(source)
            except (OSError, ValueError) as error:
                raise ValueError(f"Görsel okunamadı: {source.name}. {error}") from error
            with BytesIO() as page:
                flatten_on_white(image).save(page, format="PDF", resolution=96)
                page.seek(0)
                with PdfReader(page) as reader:
                    writer.add_page(reader.pages[0])

        first = sources[0]
        destination = first.with_name(f"{first.stem}-gorseller.pdf")
        return save_new_file(destination, writer.write)


def rotate_pages(source: Path, selection: str, degrees: int) -> Path:
    if degrees not in (90, -90, 180):
        raise ValueError("90° sağa, 90° sola veya 180° dönüş seç.")

    with read_pdf(source) as reader:
        count = len(reader.pages)
        if count == 0:
            raise ValueError("PDF’de döndürülecek sayfa yok.")
        pages = parse_pages(selection, count) if selection.strip() else range(count)
        with PdfWriter() as writer:
            writer.clone_document_from_reader(reader)
            for index in pages:
                page = writer.pages[index]
                page.rotation = (page.rotation + degrees) % 360

            destination = source.with_name(f"{source.stem}-dondurulmus.pdf")
            return save_new_file(destination, writer.write)


def split_pdf(
    source: Path,
    selection: str,
    group_size: int,
    *,
    progress: JobProgress | None = None,
) -> SavedOutputs:
    if not 1 <= group_size <= 9999:
        raise ValueError("Dosya başına 1–9999 arasında sayfa seç.")

    saved: list[Path] = []
    with read_pdf(source) as reader:
        count = len(reader.pages)
        if count == 0:
            raise ValueError("PDF’de bölünecek sayfa yok.")
        pages = parse_pages(selection, count) if selection.strip() else range(count)
        offsets = range(0, len(pages), group_size)

        try:
            for offset in tracked_items(offsets, progress):
                number = offset // group_size + 1
                destination = source.with_name(f"{source.stem}-bolum-{number:03d}.pdf")
                try:
                    with PdfWriter() as writer:
                        writer.append(reader, pages=list(pages[offset:offset + group_size]))
                        saved.append(save_new_file(destination, writer.write))
                except (OSError, PdfReadError, ValueError) as error:
                    if progress is not None:
                        progress.check_cancelled()
                    detail = f"{number}. bölüm kaydedilemedi."
                    if saved:
                        message = f"İşlem tamamlanamadı: {len(saved)} bölüm kaydedildi. {detail}"
                        return SavedOutputs(tuple(saved), message)
                    raise ValueError(detail) from error
        except JobCancelled:
            if not saved:
                raise
            return SavedOutputs(
                tuple(saved), f"İşlem iptal edildi. {len(saved)} bölüm kaydedildi."
            )

    return SavedOutputs(tuple(saved), f"{len(saved)} PDF bölümü kaydedildi.")
