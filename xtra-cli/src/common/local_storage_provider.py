from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from common.models import DownloadedResource


class LocalStorageProvider:
    def __init__(
        self,
        *,
        root_path: str,
        batch_size: int,
        read_concurrency: int,
    ) -> None:
        requested_path = Path(root_path)
        self.single_file_name: str | None = None
        self.prefix_path = ""

        if requested_path.is_file():
            self.root_path = requested_path.parent
            self.single_file_name = requested_path.name
        else:
            self.root_path = requested_path
            self.root_path.mkdir(parents=True, exist_ok=True)

        self.batch_size = batch_size
        self.read_concurrency = read_concurrency

    def iter_keys(self) -> Iterator[str]:
        if self.single_file_name is not None:
            yield self.single_file_name
            return
        for path in self.root_path.rglob("*"):
            if path.is_file():
                yield str(path.relative_to(self.root_path)).replace("\\", "/")

    def load_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[DownloadedResource]:
        resources: list[DownloadedResource] = []
        for key in keys:
            try:
                resources.append(
                    DownloadedResource(
                        key=key,
                        content=(self.root_path / key).read_bytes(),
                    )
                )
            except Exception as exc:
                errors.append(f"{key}: {exc}")
        return resources

    def load_binary_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[DownloadedResource]:
        return self.load_batch(keys=keys, errors=errors)

    def delete_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[str]:
        deleted_keys: list[str] = []
        for key in keys:
            try:
                (self.root_path / key).unlink(missing_ok=True)
                deleted_keys.append(key)
            except Exception as exc:
                errors.append(f"{key}: {exc}")
        return deleted_keys

    def describe_location(self) -> str:
        if self.single_file_name is not None:
            return str(self.root_path / self.single_file_name)
        return str(self.root_path)
