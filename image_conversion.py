"""Görselleri kaynak dosyayı koruyarak dönüştürür ve küçültür."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageOps

FORMATS = {"PNG": ".png", "JPG": ".jpg", "WebP": ".webp"}
SOURCE_FORMATS = {"PNG": "PNG", "JPEG": "JPG", "WEBP": "WebP"}


def convert_image(
    source: Path, output_format: str | None, *, scale_percent: int | None = None
) -> Path:
    """Tamamlanan çıktıyı boş bir ada kaydeder."""
    if scale_percent is not None and not 1 <= scale_percent <= 99:
        raise ValueError("Küçültme oranı %1 ile %99 arasında olmalı.")
    with Image.open(source) as original:
        if getattr(original, "is_animated", False):
            raise ValueError("Hareketli görseller henüz desteklenmiyor.")
        if output_format is None:
            output_format = SOURCE_FORMATS.get(original.format or "", "PNG")
        image = ImageOps.exif_transpose(original).convert("RGBA")

    extension = FORMATS[output_format]
    stem = source.stem
    if scale_percent is not None:
        width = max(1, round(image.width * scale_percent / 100))
        height = max(1, round(image.height * scale_percent / 100))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        stem = f"{stem}-{scale_percent}pct"

    if output_format == "JPG":
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        image = background

    with NamedTemporaryFile(dir=source.parent, prefix=".uvaia-") as temporary:
        image.save(temporary, format="JPEG" if output_format == "JPG" else output_format)
        temporary.flush()
        output = source.with_name(f"{stem}{extension}")
        index = 1
        while True:
            try:
                output.hardlink_to(temporary.name)
                return output
            except FileExistsError:
                index += 1
                output = source.with_name(f"{stem}-{index}{extension}")
