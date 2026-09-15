"""Azure Blob reader. Adapted from ceops/src/common/azure_storage_provider.py."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress

from common.models import DownloadedResource
from common.storage_configuration import AzureStorageConfiguration


class AzureBlobStorageProvider:
    def __init__(
        self,
        *,
        container_name: str,
        prefix_path: str,
        batch_size: int,
        read_concurrency: int,
        azure_configuration: AzureStorageConfiguration,
    ) -> None:
        from azure.storage.blob import BlobServiceClient

        self.container_name = container_name
        self.prefix_path = prefix_path
        self.batch_size = batch_size
        self.read_concurrency = read_concurrency
        self.service_client = BlobServiceClient.from_connection_string(
            azure_configuration.connection_string,
        )
        self.container_client = self.service_client.get_container_client(
            self.container_name,
        )

    def iter_keys(self) -> Iterator[str]:
        for blob in self.container_client.list_blobs(
            name_starts_with=self.prefix_path,
        ):
            yield blob.name

    def load_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[DownloadedResource]:
        def download(key: str) -> DownloadedResource | None:
            try:
                blob = self.container_client.get_blob_client(key)
                content = blob.download_blob().readall()
                return DownloadedResource(key=key, content=content)
            except Exception as exc:
                errors.append(f"{key}: {exc}")
                return None

        with ThreadPoolExecutor(max_workers=self.read_concurrency) as executor:
            results = list(executor.map(download, keys))
        return [result for result in results if result is not None]

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
        from azure.core.exceptions import ResourceNotFoundError

        deleted_keys: list[str] = []

        def delete_one(key: str) -> str:
            with suppress(ResourceNotFoundError):
                self.container_client.delete_blob(key)
            return key

        with ThreadPoolExecutor(max_workers=self.read_concurrency) as executor:
            futures = {executor.submit(delete_one, key): key for key in keys}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    deleted_keys.append(future.result())
                except Exception as exc:
                    errors.append(f"{key}: {exc}")
        return deleted_keys

    def describe_location(self) -> str:
        if self.prefix_path:
            return f"azure://{self.container_name}/{self.prefix_path}"
        return f"azure://{self.container_name}"
