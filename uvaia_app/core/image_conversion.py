"""Görselleri kaynak dosyayı koruyarak düzenler ve dönüştürür."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageEnhance, ImageOps

from uvaia_app.core.job_progress import JobCancelled, JobProgress, tracked_items
from uvaia_app.core.output_files import SavedOutputs, save_new_file

FORMATS = {"PNG": ".png", "JPG": ".jpg", "WebP": ".webp", "TIFF": ".tiff", "BMP": ".bmp", "AVIF": ".avif"}
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


@dataclass(frozen=True)
class ImageAdjustments:
    brightness: int = 100
    contrast: int = 100
    saturation: int = 100

    def __post_init__(self) -> None:
        if not all(0 <= value <= 200 for value in (self.brightness, self.contrast, self.saturation)):
            raise ValueError("Görsel ayarları 0–200 arasında olmalı.")

    def apply(self, image: Image.Image) -> Image.Image:
        alpha = image.getchannel("A")
        adjusted = image.convert("RGB")
        for value, enhancer in (
            (self.brightness, ImageEnhance.Brightness),
            (self.contrast, ImageEnhance.Contrast),
            (self.saturation, ImageEnhance.Color),
        ):
            if value != 100:
                adjusted = enhancer(adjusted).enhance(value / 100)
        adjusted.putalpha(alpha)
        return adjusted


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

    destination = source.with_name(f"{stem}{extension}")
    return save_image_copy(image, destination, output_format)


def save_image_copy(image: Image.Image, destination: Path, output_format: str) -> Path:
    if output_format in ("JPG", "BMP"):
        image = flatten_on_white(image)
    pillow_format = "JPEG" if output_format == "JPG" else output_format
    return save_new_file(destination, lambda stream: image.save(stream, format=pillow_format))


def adjust_image(source: Path, settings: ImageAdjustments) -> Path:
    image, source_format = read_still_image(source)
    output_format = SOURCE_FORMATS.get(source_format or "", "PNG")
    destination = source.with_name(f"{source.stem}-ayarli{FORMATS[output_format]}")
    return save_image_copy(settings.apply(image), destination, output_format)


def convert_images(
    sources: tuple[Path, ...],
    output_format: str,
    *,
    progress: JobProgress | None = None,
) -> SavedOutputs:
    """Hatalı dosyaları atlayarak seçilen görselleri sırayla dönüştürür."""
    saved: list[Path] = []
    failed: list[str] = []
    try:
        for source in tracked_items(sources, progress):
            try:
                saved.append(convert_image(source, output_format))
            except (OSError, ValueError, Image.DecompressionBombError):
                failed.append(source.name)
    except JobCancelled:
        if not saved:
            raise
        message = f"İşlem iptal edildi. {len(saved)} görsel kaydedildi."
        return SavedOutputs(tuple(saved), message)

    if failed:
        issue = f"{len(failed)} dosya dönüştürülemedi. İlk hata: {failed[0]}"
        if not saved:
            raise ValueError(issue)
        message = f"{len(saved)}/{len(sources)} görsel {output_format} olarak kaydedildi. {issue}"
    else:
        message = f"{len(saved)} görsel {output_format} olarak kaydedildi."
    return SavedOutputs(tuple(saved), message)


def compress_image(source: Path, output_format: str, quality: int) -> Path:
    """Boyutları korur ve yalnızca daha küçük bir dosya elde edilirse kaydeder."""
    if output_format not in ("JPG", "WebP") or not 1 <= quality <= 95:
        raise ValueError("JPG veya WebP seç ve kaliteyi 1–95 arasında gir.")

    source_size = source.stat().st_size
    image, _ = read_still_image(source)
    if output_format in ("JPG", "BMP"):
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
