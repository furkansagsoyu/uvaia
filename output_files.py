"""Tamamlanan çıktıları var olan dosyalara dokunmadan kaydeder."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO


def save_new_file(destination: Path, write: Callable[[BinaryIO], object]) -> Path:
    """Yazma tamamlanınca kullanılabilir ilk çıktı adını ayırır."""
    with NamedTemporaryFile(dir=destination.parent, prefix=".uvaia-") as temporary:
        write(temporary)
        temporary.flush()
        output = destination
        index = 1
        while True:
            try:
                output.hardlink_to(temporary.name)
                return output
            except FileExistsError:
                index += 1
                output = destination.with_name(
                    f"{destination.stem}-{index}{destination.suffix}"
                )
