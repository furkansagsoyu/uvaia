"""Görsel bilgilerini gösterir ve temiz bir PNG kopyası oluşturur."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import ExifTags, Image, ImageCms, ImageOps

from output_files import save_new_file

ICC_MODES = {"RGB": "RGB", "GRAY": "L", "CMYK": "CMYK", "Lab": "LAB"}


def inspect_image(source: Path) -> str:
    with Image.open(source) as image:
        exif = image.getexif()
        info = image.info
        lines = [
            source.name,
            f"Biçim: {image.format}",
            f"Piksel boyutu: {image.width} × {image.height}",
            f"Dosya boyutu: {source.stat().st_size:,} bayt",
            f"EXIF: {'var' if exif else 'yok'}",
            f"EXIF konum etiketi: {'var' if ExifTags.IFD.GPSInfo in exif else 'yok'}",
            f"ICC renk profili: {'var' if info.get('icc_profile') else 'yok'}",
        ]
        camera = " ".join(
            str(exif.get(tag, "")).strip() for tag in (ExifTags.Base.Make, ExifTags.Base.Model)
        ).strip()
        if camera:
            lines.append(f"Kamera: {camera[:160]}")
        if getattr(image, "is_animated", False):
            lines.append(f"Kare sayısı: {image.n_frames}")
    return "\n".join(lines)


def convert_profile(image: Image.Image, profile_data: bytes) -> Image.Image:
    try:
        profile = ImageCms.getOpenProfile(BytesIO(profile_data))
        mode = ICC_MODES.get(profile.profile.xcolor_space.strip())
        if mode is None:
            raise ValueError("Desteklenmeyen renk profili.")
        return ImageCms.profileToProfile(
            image.convert(mode),
            profile,
            ImageCms.createProfile("sRGB"),
            outputMode="RGB",
        )
    except (ImageCms.PyCMSError, OSError, ValueError) as error:
        raise ValueError("Görselin renk profili sRGB’ye dönüştürülemedi.") from error


def save_clean_png(source: Path) -> Path:
    with Image.open(source) as original:
        if getattr(original, "is_animated", False):
            raise ValueError("Meta verisiz PNG için hareketsiz bir görsel seç.")
        image = ImageOps.exif_transpose(original)
        profile = image.info.get("icc_profile")
        if image.mode.startswith("I;16") and not profile:
            pixels = image.convert("I;16")
        else:
            pixels = convert_profile(image, profile) if profile else image.convert("RGB")
            alpha = image.convert("RGBA").getchannel("A")
            if alpha.getextrema() != (255, 255):
                pixels.putalpha(alpha)
        clean = Image.frombytes(pixels.mode, pixels.size, pixels.tobytes())

    destination = source.with_name(f"{source.stem}-temiz.png")
    return save_new_file(destination, lambda stream: clean.save(stream, format="PNG"))
