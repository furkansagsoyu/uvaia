"""ZIP dosyalarını oluşturur ve denetlenen bir klasöre açar."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from job_progress import JobProgress, tracked_items
from output_files import save_new_file

MAX_MEMBERS = 10_000
MAX_EXPANDED_BYTES = 8 * 1024 ** 3
COPY_CHUNK = 1024 * 1024


def member_parts(filename: str) -> tuple[str, ...]:
    parts = tuple(filename.removesuffix("/").split("/"))
    if (
        "\\" in filename
        or "\0" in filename
        or any(part in ("", ".", "..") for part in parts)
        or (len(parts[0]) >= 2 and parts[0][1] == ":")
    ):
        raise ValueError("ZIP içinde geçersiz bir dosya yolu var.")
    return parts


def copy_data(source: BinaryIO, output: BinaryIO, progress: JobProgress | None) -> None:
    while chunk := source.read(COPY_CHUNK):
        if progress is not None:
            progress.check_cancelled()
        output.write(chunk)


def create_zip(sources: tuple[Path, ...], *, progress: JobProgress | None = None) -> Path:
    if not sources or len(sources) > MAX_MEMBERS:
        raise ValueError(f"ZIP oluşturmak için 1–{MAX_MEMBERS} arasında dosya seç.")

    def write_zip(stream: BinaryIO) -> None:
        used: set[str] = set()
        with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
            for source in tracked_items(sources, progress):
                if not source.is_file():
                    raise ValueError(f"Dosya okunamadı: {source.name}")
                name = source.name
                member_parts(name)
                number = 1
                while name in used:
                    number += 1
                    name = f"{source.stem}-{number}{source.suffix}"
                used.add(name)
                entry = ZipInfo.from_file(source, arcname=name, strict_timestamps=False)
                entry.compress_type = ZIP_DEFLATED
                with source.open("rb") as contents, archive.open(entry, "w", force_zip64=True) as out:
                    copy_data(contents, out, progress)

        if progress is not None:
            progress.check_cancelled()

    first = sources[0]
    destination = first.with_name(f"{first.stem}-arsiv.zip")
    return save_new_file(destination, write_zip)


def validate_members(archive: ZipFile, destination: Path) -> list[tuple[ZipInfo, tuple[str, ...]]]:
    members = archive.infolist()
    if not members or len(members) > MAX_MEMBERS:
        raise ValueError(f"ZIP içinde 1–{MAX_MEMBERS} arasında öğe olmalı.")
    size = sum(member.file_size for member in members)
    if size > MAX_EXPANDED_BYTES:
        raise ValueError("ZIP’in açılmış boyutu 8 GiB sınırını aşıyor.")
    if size > shutil.disk_usage(destination).free:
        raise ValueError("ZIP’i açmak için yeterli disk alanı yok.")

    seen: set[tuple[str, ...]] = set()
    entries = []
    for member in members:
        parts = member_parts(member.orig_filename)
        if parts in seen:
            raise ValueError("ZIP aynı yolu birden fazla kez içeriyor.")
        seen.add(parts)
        expected_mode = stat.S_IFDIR if member.is_dir() else stat.S_IFREG
        if stat.S_IFMT(member.external_attr >> 16) not in (0, expected_mode):
            raise ValueError("ZIP bağlantı veya özel dosya içeriyor.")
        if member.flag_bits & 1:
            raise ValueError("Şifreli ZIP bu araçla açılamıyor.")
        entries.append((member, parts))
    return entries


def publish_directory(stage: Path, destination: Path) -> Path:
    output = destination
    index = 1
    while True:
        try:
            output.mkdir(mode=0o700)
            break
        except FileExistsError:
            index += 1
            output = destination.with_name(f"{destination.name}-{index}")
    try:
        return stage.replace(output)
    except OSError:
        output.rmdir()
        raise


def extract_zip(source: Path, *, progress: JobProgress | None = None) -> Path:
    try:
        with ZipFile(source) as archive:
            entries = validate_members(archive, source.parent)
            with TemporaryDirectory(dir=source.parent, prefix=".uvaia-zip-") as temporary:
                stage = Path(temporary) / "dosyalar"
                stage.mkdir(mode=0o700)
                for member, parts in tracked_items(entries, progress):
                    output = stage.joinpath(*parts)
                    if member.is_dir():
                        output.mkdir(parents=True, exist_ok=True)
                    else:
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as contents, output.open("xb") as stream:
                            copy_data(contents, stream, progress)

                if progress is not None:
                    progress.check_cancelled()
                destination = source.with_name(f"{source.stem}-acilan")
                return publish_directory(stage, destination)
    except (BadZipFile, RuntimeError) as error:
        raise ValueError("ZIP okunamadı veya desteklenmeyen sıkıştırma kullanıyor.") from error
