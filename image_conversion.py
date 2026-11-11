"""Görselleri kaynak dosyayı koruyarak dönüştürür."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageOps

FORMATS = {"PNG": ".png", "JPG": ".jpg", "WebP": ".webp"}


def convert_image(source: Path, output_format: str) -> Path:
    """Tamamlanan çıktıyı boş bir ada kaydeder."""
    extension = FORMATS[output_format]
    with Image.open(source) as original:
        if getattr(original, "is_animated", False):
            raise ValueError("Hareketli görseller henüz desteklenmiyor.")
        image = ImageOps.exif_transpose(original).convert("RGBA")

    if output_format == "JPG":
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        image = background

    with NamedTemporaryFile(dir=source.parent, prefix=".uvaia-") as temporary:
        image.save(temporary, format="JPEG" if output_format == "JPG" else output_format)
        temporary.flush()
        output = source.with_suffix(extension)
        index = 1
        while True:
            try:
                output.hardlink_to(temporary.name)
                return output
            except FileExistsError:
                index += 1
                output = source.with_name(f"{source.stem}-{index}{extension}")
