from __future__ import annotations

from contextlib import AbstractContextManager
from typing import BinaryIO, Protocol


class StorageWriter(Protocol):
    def upload_batch(
        self,
        *,
        key_contents: dict[str, bytes | str],
        content_type: str,
        errors: list[str],
    ) -> list[str]: ...

    def open_binary_writer(
        self,
        *,
        key: str,
        content_type: str,
    ) -> AbstractContextManager[BinaryIO]: ...

    def delete_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[str]: ...

    def describe_location(self) -> str: ...
