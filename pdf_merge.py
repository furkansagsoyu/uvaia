"""Seçilen PDF'leri listedeki sırayla tek bir dosyada birleştirir."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from output_files import save_new_file


def merge_pdfs(sources: list[Path]) -> Path:
    if len(sources) < 2:
        raise ValueError("En az iki PDF seç.")

    with PdfWriter() as writer:
        for index, source in enumerate(sources, start=1):
            try:
                with PdfReader(source) as reader:
                    if reader.is_encrypted:
                        raise ValueError(f"Şifreli PDF birleştirilemiyor: {source.name}")
                    if reader.get_fields():
                        reader.add_form_topname(f"Belge{index}")
                    writer.append(reader)
            except (PdfReadError, OSError) as error:
                raise ValueError(f"PDF okunamadı: {source.name}") from error

        first = sources[0]
        destination = first.with_name(f"{first.stem}-birlesik.pdf")
        return save_new_file(destination, writer.write)
