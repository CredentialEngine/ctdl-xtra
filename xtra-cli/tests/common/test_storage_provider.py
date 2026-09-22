from __future__ import annotations

from typing import get_type_hints

from common.local_storage_provider import LocalStorageProvider
from common.storage_provider import StorageProvider


def test_storage_provider_protocol_lists_batch_methods() -> None:
    names = set(StorageProvider.__dict__) | set(dir(StorageProvider))
    for method in (
        "iter_keys",
        "load_batch",
        "load_binary_batch",
        "delete_batch",
        "describe_location",
    ):
        assert method in names


def test_local_provider_matches_protocol_shape(tmp_path) -> None:
    provider = LocalStorageProvider(
        root_path=str(tmp_path), batch_size=10, read_concurrency=1
    )
    for method in (
        "iter_keys",
        "load_batch",
        "load_binary_batch",
        "delete_batch",
        "describe_location",
    ):
        assert callable(getattr(provider, method))
    assert get_type_hints(StorageProvider.load_batch)
