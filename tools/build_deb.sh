#!/usr/bin/env bash
# Linux Mint üzerinde bağımsız bir Uvaia .deb paketi oluşturur.
set -euo pipefail
cd "$(dirname "$0")/.."
version=${1:-0.1.0}
architecture=$(dpkg --print-architecture)
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
mkdir -p dist
.venv/bin/python -m PyInstaller --noconfirm --onedir --name uvaia \
    --workpath "$build/work" --distpath "$build/dist" --specpath "$build" \
    --add-data "$PWD/assets:assets" --collect-data imageio_ffmpeg \
    --collect-all pypdfium2_raw uvaia.py
package="$build/package"
install -d "$package/DEBIAN" "$package/opt" "$package/usr/bin" \
    "$package/usr/share/applications" "$package/usr/share/icons/hicolor/256x256/apps"
cp -a "$build/dist/uvaia" "$package/opt/uvaia"
ln -s /opt/uvaia/uvaia "$package/usr/bin/uvaia"
install -m 644 assets/uvaia.png \
    "$package/usr/share/icons/hicolor/256x256/apps/io.github.furkansagsoyu.Uvaia.png"
cat > "$package/usr/share/applications/io.github.furkansagsoyu.Uvaia.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Uvaia
Comment=Yerel dosya araçları
Exec=uvaia
Icon=io.github.furkansagsoyu.Uvaia
Terminal=false
Categories=Graphics;
DESKTOP
cat > "$package/DEBIAN/control" <<CONTROL
Package: uvaia
Version: $version
Architecture: $architecture
Maintainer: Uvaia geliştiricileri
Depends: libc6 (>= 2.39), libgl1, libegl1, libxkbcommon-x11-0, libxcb-cursor0, libpulse0, fonts-dejavu-core
Suggests: tesseract-ocr, tesseract-ocr-tur, tesseract-ocr-eng
Section: graphics
Priority: optional
Description: Linux Mint için yerel dosya araçları
 Görsel, PDF, video, ses ve ZIP dosyalarını düzenler.
CONTROL
dpkg-deb --root-owner-group -Zzstd --build "$package" "dist/uvaia_${version}_${architecture}.deb"
