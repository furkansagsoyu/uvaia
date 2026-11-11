"""Görselleri kaynak dosyayı koruyarak düzenler ve dönüştürür."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps

from output_files import save_new_file

FORMATS = {"PNG": ".png", "JPG": ".jpg", "WebP": ".webp"}
SOURCE_FORMATS = {"PNG": "PNG", "JPEG": "JPG", "WEBP": "WebP"}
CropBounds = tuple[float, float, float, float]
ROTATIONS = (None, Image.Transpose.ROTATE_270, Image.Transpose.ROTATE_180, Image.Transpose.ROTATE_90)


@dataclass(frozen=True)
class Orientation:
    """Önce saat yönünde dönüşü, ardından yatay yansıtmayı uygular."""

    turns: int = 0
    mirrored: bool = False

    def rotate(self, turns: int) -> Orientation:
        direction = -turns if self.mirrored else turns
        return Orientation((self.turns + direction) % 4, self.mirrored)

    def flip_horizontal(self) -> Orientation:
        return Orientation(self.turns, not self.mirrored)

    def flip_vertical(self) -> Orientation:
        return Orientation((self.turns + 2) % 4, not self.mirrored)


def read_still_image(source: Path) -> tuple[Image.Image, str | None]:
    with Image.open(source) as original:
        if getattr(original, "is_animated", False):
            raise ValueError("Hareketli görseller henüz desteklenmiyor.")
        return ImageOps.exif_transpose(original).convert("RGBA"), original.format


def flatten_on_white(image: Image.Image) -> Image.Image:
    background = Image.new("RGB", image.size, "white")
    background.paste(image, mask=image.getchannel("A"))
    return background


def convert_image(
    source: Path,
    output_format: str | None,
    *,
    scale_percent: int | None = None,
    crop_bounds: CropBounds | None = None,
    orientation: Orientation | None = None,
) -> Path:
    """Tamamlanan çıktıyı boş bir ada kaydeder."""
    if scale_percent is not None and not 1 <= scale_percent <= 99:
        raise ValueError("Küçültme oranı %1 ile %99 arasında olmalı.")
    image, source_format = read_still_image(source)
    if output_format is None:
        output_format = SOURCE_FORMATS.get(source_format or "", "PNG")

    extension = FORMATS[output_format]
    stem = source.stem
    if scale_percent is not None:
        width = max(1, round(image.width * scale_percent / 100))
        height = max(1, round(image.height * scale_percent / 100))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        stem = f"{stem}-{scale_percent}pct"

    if crop_bounds is not None:
        left, top, right, bottom = crop_bounds
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError("Geçerli bir kırpma alanı seç.")
        x = min(image.width - 1, round(left * image.width))
        y = min(image.height - 1, round(top * image.height))
        right_edge = max(x + 1, round(right * image.width))
        bottom_edge = max(y + 1, round(bottom * image.height))
        image = image.crop((x, y, right_edge, bottom_edge))
        stem = f"{stem}-kirpilmis"

    if orientation is not None:
        rotation = ROTATIONS[orientation.turns]
        if rotation is not None:
            image = image.transpose(rotation)
        if orientation.mirrored:
            image = ImageOps.mirror(image)
        stem = f"{stem}-duzenlenmis"

    if output_format == "JPG":
        image = flatten_on_white(image)

    destination = source.with_name(f"{stem}{extension}")
    pillow_format = "JPEG" if output_format == "JPG" else output_format
    return save_new_file(destination, lambda stream: image.save(stream, format=pillow_format))


def convert_images(sources: tuple[Path, ...], output_format: str) -> str:
    """Hatalı dosyaları atlayarak seçilen görselleri sırayla dönüştürür."""
    converted = 0
    failed: list[str] = []
    for source in sources:
        try:
            convert_image(source, output_format)
        except (OSError, ValueError, Image.DecompressionBombError):
            failed.append(source.name)
        else:
            converted += 1

    if failed:
        issue = f"{len(failed)} dosya dönüştürülemedi. İlk hata: {failed[0]}"
        if converted == 0:
            raise ValueError(issue)
        return f"{converted}/{len(sources)} görsel {output_format} olarak kaydedildi. {issue}"
    return f"{converted} görsel {output_format} olarak kaydedildi."


def compress_image(source: Path, output_format: str, quality: int) -> Path:
    """Boyutları korur ve yalnızca daha küçük bir dosya elde edilirse kaydeder."""
    if output_format not in ("JPG", "WebP") or not 1 <= quality <= 95:
        raise ValueError("JPG veya WebP seç ve kaliteyi 1–95 arasında gir.")

    source_size = source.stat().st_size
    image, _ = read_still_image(source)
    if output_format == "JPG":
        image = flatten_on_white(image)
        pillow_format = "JPEG"
        options = {"quality": quality, "optimize": True}
    else:
        pillow_format = "WebP"
        options = {"quality": quality, "method": 6}

    def encode(stream: BinaryIO) -> None:
        image.save(stream, format=pillow_format, **options)
        if stream.tell() >= source_size:
            raise ValueError("Çıktı kaynak dosyadan küçük olmadı. Daha düşük kalite dene.")

    destination = source.with_name(f"{source.stem}-sikistirilmis{FORMATS[output_format]}")
    return save_new_file(destination, encode)
