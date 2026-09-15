from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


class LocalStorageWriter:
    def __init__(self, *, root_path: str, write_concurrency: int) -> None:
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self.write_concurrency = write_concurrency
        self.prefix_path = ""

    def upload_batch(
        self,
        *,
        key_contents: dict[str, bytes | str],
        content_type: str,
        errors: list[str],
    ) -> list[str]:
        uploaded_keys: list[str] = []

        def write_one(key: str, content: bytes | str) -> str:
            path = self.root_path / key
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                content = content.encode("utf-8")
            path.write_bytes(content)
            return key

        with ThreadPoolExecutor(max_workers=self.write_concurrency) as executor:
            futures = {
                executor.submit(write_one, key, content): key
                for key, content in key_contents.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    uploaded_keys.append(future.result())
                except Exception as exc:
                    errors.append(f"{key}: {exc}")
        return uploaded_keys

    @contextmanager
    def open_binary_writer(
        self,
        *,
        key: str,
        content_type: str,
    ) -> Iterator[BinaryIO]:
        path = self.root_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            yield stream

    def delete_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[str]:
        deleted_keys: list[str] = []

        def delete_one(key: str) -> str:
            (self.root_path / key).unlink(missing_ok=True)
            return key

        with ThreadPoolExecutor(max_workers=self.write_concurrency) as executor:
            futures = {executor.submit(delete_one, key): key for key in keys}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    deleted_keys.append(future.result())
                except Exception as exc:
                    errors.append(f"{key}: {exc}")
        return deleted_keys

    def describe_location(self) -> str:
        return str(self.root_path)
