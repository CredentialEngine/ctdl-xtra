from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from common.models import DownloadedResource


class StorageProvider(Protocol):
    def iter_keys(self) -> Iterator[str]: ...

    def load_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[DownloadedResource]: ...

    def load_binary_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[DownloadedResource]: ...

    def delete_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[str]: ...

    def describe_location(self) -> str: ...
