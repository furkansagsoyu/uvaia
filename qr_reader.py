"""Hareketsiz görsellerdeki QR kodlarını yerel olarak okur."""

from __future__ import annotations

from pathlib import Path

import zxingcpp

from image_conversion import flatten_on_white, read_still_image


def read_qr_codes(source: Path) -> str:
    image, _ = read_still_image(source)
    codes = zxingcpp.read_barcodes(
        flatten_on_white(image).convert("L"),
        formats=zxingcpp.BarcodeFormat.QRCode,
        text_mode=zxingcpp.TextMode.Plain,
    )
    if not codes:
        raise ValueError("Görselde QR kodu bulunamadı.")

    payloads = []
    for code in codes:
        if code.content_type == zxingcpp.ContentType.Binary:
            payloads.append(f"İkili veri (hex): {code.bytes.hex(' ')}")
        else:
            payloads.append(code.text or "Boş QR kodu")
    return "\n\n".join(payloads)
