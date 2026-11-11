"""Görsellerde ve PDF sayfalarında QR kodlarını yerel olarak okur."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import zxingcpp
from PIL import Image

from image_conversion import flatten_on_white, read_still_image
from pdf_render import open_pdf_document, page_image, page_indices


def decode_qr_codes(image: Image.Image) -> list[str]:
    codes = zxingcpp.read_barcodes(
        image.convert("L"),
        formats=zxingcpp.BarcodeFormat.QRCode,
        text_mode=zxingcpp.TextMode.Plain,
    )
    payloads = []
    for code in codes:
        if code.content_type == zxingcpp.ContentType.Binary:
            payloads.append(f"İkili veri (hex): {code.bytes.hex(' ')}")
        else:
            payloads.append(code.text or "Boş QR kodu")
    return payloads


def read_qr_codes(source: Path) -> str:
    image, _ = read_still_image(source)
    payloads = decode_qr_codes(flatten_on_white(image))
    if not payloads:
        raise ValueError("Görselde QR kodu bulunamadı.")
    return "\n\n".join(payloads)


def read_pdf_qr_codes(source: Path, selection: str) -> str:
    results = []
    with closing(open_pdf_document(source)) as document:
        for index in page_indices(document, selection):
            with page_image(document, index) as image:
                payloads = decode_qr_codes(image)
            if payloads:
                results.append(f"Sayfa {index + 1}\n" + "\n\n".join(payloads))
    if not results:
        raise ValueError("Seçilen PDF sayfalarında QR kodu bulunamadı.")
    return "\n\n".join(results)
