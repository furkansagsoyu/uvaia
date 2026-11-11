"""Arka plan işlerinin sayfa ilerlemesini ve iptal isteğini iletir."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass


class JobCancelled(Exception):
    """Kullanıcı işlemi durdurdu."""


@dataclass(frozen=True)
class JobProgress:
    report: Callable[[int, int], None]
    is_cancelled: Callable[[], bool]

    def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise JobCancelled


def tracked_pages(pages: Sequence[int], progress: JobProgress | None) -> Iterator[int]:
    if progress is None:
        yield from pages
        return

    total = len(pages)
    progress.report(0, total)
    for completed, index in enumerate(pages, start=1):
        progress.check_cancelled()
        yield index
        progress.check_cancelled()
        progress.report(completed, total)
