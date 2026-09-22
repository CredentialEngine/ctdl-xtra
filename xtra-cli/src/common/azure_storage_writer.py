"""Azure Blob writer. Adapted from ceops/src/common/azure_storage_writer.py."""

from __future__ import annotations

import io
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, suppress
from typing import BinaryIO


class AzureBlobUploadWriter(io.RawIOBase):
    def __init__(
        self,
        *,
        blob_client,
        content_type: str,
        chunk_size: int = 4 * 1024 * 1024,
    ) -> None:
        from azure.storage.blob import ContentSettings

        self.blob_client = blob_client
        self.content_type = content_type
        self.chunk_size = chunk_size
        self.buffer = bytearray()
        self.block_ids: list[str] = []
        self.block_number = 0
        self.closed_flag = False
        self._content_settings = ContentSettings

    def writable(self) -> bool:
        return True

    def write(self, b) -> int:
        if self.closed_flag:
            raise ValueError("I/O operation on closed writer")
        chunk = bytes(b)
        self.buffer.extend(chunk)
        while len(self.buffer) >= self.chunk_size:
            self._flush_chunk()
        return len(chunk)

    def _flush_chunk(self) -> None:
        chunk = bytes(self.buffer[: self.chunk_size])
        del self.buffer[: self.chunk_size]
        block_id = f"{self.block_number:08d}"
        self.block_number += 1
        self.blob_client.stage_block(block_id=block_id, data=chunk)
        self.block_ids.append(block_id)

    def close(self) -> None:
        if self.closed_flag:
            return
        try:
            if self.buffer:
                block_id = f"{self.block_number:08d}"
                self.blob_client.stage_block(
                    block_id=block_id,
                    data=bytes(self.buffer),
                )
                self.block_ids.append(block_id)
                self.buffer.clear()
            self.blob_client.commit_block_list(
                self.block_ids,
                content_settings=self._content_settings(
                    content_type=self.content_type
                ),
            )
        finally:
            self.closed_flag = True
            super().close()


class AzureBlobStorageWriter:
    def __init__(
        self,
        *,
        container_name: str,
        prefix_path: str,
        write_concurrency: int,
        connection_string: str,
    ) -> None:
        from azure.core.exceptions import HttpResponseError, ResourceExistsError
        from azure.storage.blob import BlobServiceClient

        if not connection_string:
            raise ValueError("Azure storage connection string is required")

        self.container_name = container_name
        self.prefix_path = prefix_path
        self.write_concurrency = write_concurrency
        self.blob_service_client = BlobServiceClient.from_connection_string(
            connection_string
        )
        self.container_client = self.blob_service_client.get_container_client(
            container_name
        )
        try:
            self.container_client.create_container()
        except ResourceExistsError:
            pass
        except HttpResponseError:
            pass

    def _blob_key(self, key: str) -> str:
        if self.prefix_path:
            return f"{self.prefix_path.rstrip('/')}/{key.lstrip('/')}"
        return key

    def upload_batch(
        self,
        *,
        key_contents: dict[str, bytes | str],
        content_type: str,
        errors: list[str],
    ) -> list[str]:
        from azure.storage.blob import ContentSettings

        uploaded_keys: list[str] = []

        def upload_one(key: str, content: bytes | str) -> str:
            blob_key = self._blob_key(key)
            blob_client = self.container_client.get_blob_client(blob_key)
            blob_client.upload_blob(
                content,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
            return blob_key

        with ThreadPoolExecutor(max_workers=self.write_concurrency) as executor:
            futures = {
                executor.submit(upload_one, key, content): key
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
        blob_key = self._blob_key(key)
        blob_client = self.container_client.get_blob_client(blob_key)
        with AzureBlobUploadWriter(
            blob_client=blob_client,
            content_type=content_type,
        ) as writer:
            yield writer

    def delete_batch(
        self,
        *,
        keys: list[str],
        errors: list[str],
    ) -> list[str]:
        from azure.core.exceptions import ResourceNotFoundError

        deleted_keys: list[str] = []

        def delete_one(key: str) -> str:
            blob_key = self._blob_key(key)
            with suppress(ResourceNotFoundError):
                self.container_client.delete_blob(blob_key)
            return blob_key

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
        if not self.prefix_path:
            return f"azure://{self.container_name}"
        return f"azure://{self.container_name}/{self.prefix_path}"
