"""Arka plan işlerinin sayfa ilerlemesini ve iptal isteğini iletir."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import TypeVar

Item = TypeVar("Item")


class JobCancelled(Exception):
    """Kullanıcı işlemi durdurdu."""


@dataclass(frozen=True)
class JobProgress:
    report: Callable[[int, int], None]
    is_cancelled: Callable[[], bool]

    def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise JobCancelled


def tracked_items(
    items: Sequence[Item], progress: JobProgress | None
) -> Iterator[Item]:
    if progress is None:
        yield from items
        return

    total = len(items)
    progress.report(0, total)
    for completed, item in enumerate(items, start=1):
        progress.check_cancelled()
        yield item
        progress.check_cancelled()
        progress.report(completed, total)
