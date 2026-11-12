"""Uvaia’yı Cinnamon menüsüne ve Nemo sağ tık menüsüne ekler."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

APP_ID = "io.github.furkansagsoyu.Uvaia"
ICON = APP_ID
EXTENSIONS = "png;jpg;jpeg;webp;bmp;tif;tiff;gif;avif;ico;pdf;mp4;mkv;mov;webm;avi;mp3;wav;flac;m4a;aac;ogg;opus;aif;aiff;zip;"


def desktop_argument(path: Path) -> str:
    """Bir komut argümanını Exec ve anahtar dosyası kurallarına göre yazar."""
    value = str(path).replace("%", "%%")
    quoted = "".join("\\" + char if char in '\\"$`' else char for char in value)
    escaped = quoted.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'


def data_home() -> Path:
    configured = Path(os.environ.get("XDG_DATA_HOME", ""))
    if configured.is_absolute():
        return configured
    return Path.home() / ".local" / "share"


def install(data_dir: Path, python: Path, app: Path) -> tuple[Path, Path]:
    command = f"{desktop_argument(python)} {desktop_argument(app)}"
    desktop = data_dir / "applications" / f"{APP_ID}.desktop"
    nemo = data_dir / "nemo" / "actions" / f"{APP_ID}.nemo_action"

    icon = data_dir / "icons" / "hicolor" / "256x256" / "apps" / f"{ICON}.png"
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(app.parent / "assets" / "uvaia.png", icon)

    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(
        f"""[Desktop Entry]
Type=Application
Name=Uvaia
Comment=Yerel görsel, PDF, video, ses ve arşiv araçları
Exec={command}
Icon={ICON}
Terminal=false
Categories=Graphics;
""",
        encoding="utf-8",
    )

    nemo.parent.mkdir(parents=True, exist_ok=True)
    nemo.write_text(
        f"""[Nemo Action]
Name=Uvaia ile aç
Comment=Seçili dosyaları Uvaia’ya gönder
Exec={command} -- %F
Icon-Name={ICON}
Selection=notnone
Extensions={EXTENSIONS}
Quote=double
UriScheme=file
""",
        encoding="utf-8",
    )
    return desktop, nemo


def remove(data_dir: Path) -> None:
    (data_dir / "icons" / "hicolor" / "256x256" / "apps" / f"{ICON}.png").unlink(missing_ok=True)
    (data_dir / "applications" / f"{APP_ID}.desktop").unlink(missing_ok=True)
    (data_dir / "nemo" / "actions" / f"{APP_ID}.nemo_action").unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true", help="Menü girdilerini kaldır.")
    args = parser.parse_args()

    if args.remove:
        remove(data_home())
        print("Uvaia menü girdileri kaldırıldı.")
    else:
        python = Path(sys.executable).absolute()
        app = Path(__file__).resolve().with_name("uvaia.py")
        if not app.is_file():
            parser.error("uvaia.py bulunamadı.")
        desktop, nemo = install(data_home(), python, app)
        print(f"Cinnamon: {desktop}")
        print(f"Nemo: {nemo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
