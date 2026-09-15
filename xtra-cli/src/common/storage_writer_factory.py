from __future__ import annotations

from urllib.parse import urlparse

from common.local_storage_writer import LocalStorageWriter
from common.storage_uri import (
    parse_azure_storage_uri,
    parse_file_storage_uri,
    parse_local_path_if_supported,
)
from common.storage_writer import StorageWriter


def create_storage_writer(
    *,
    target_uri: str,
    write_concurrency: int,
    azure_storage_connection_string: str | None = None,
) -> StorageWriter:
    parsed = urlparse(target_uri)
    scheme = parsed.scheme.lower()

    if scheme == "azure":
        if not azure_storage_connection_string:
            raise ValueError("Azure storage connection string is required")
        from common.azure_storage_writer import AzureBlobStorageWriter

        azure_uri = parse_azure_storage_uri(target_uri)
        return AzureBlobStorageWriter(
            container_name=azure_uri.container_name,
            prefix_path=azure_uri.prefix_path,
            write_concurrency=write_concurrency,
            connection_string=azure_storage_connection_string,
        )

    if scheme == "file":
        file_uri = parse_file_storage_uri(target_uri)
        return LocalStorageWriter(
            root_path=file_uri.local_path,
            write_concurrency=write_concurrency,
        )

    local_path = parse_local_path_if_supported(target_uri)
    if local_path:
        return LocalStorageWriter(
            root_path=local_path,
            write_concurrency=write_concurrency,
        )

    raise ValueError(f"Unsupported storage URI: {target_uri}")
