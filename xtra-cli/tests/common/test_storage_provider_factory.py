from __future__ import annotations

import pytest

from common.local_storage_provider import LocalStorageProvider
from common.storage_provider_factory import create_storage_provider


def test_factory_uses_file_uri(tmp_path) -> None:
    provider = create_storage_provider(
        source_uri=tmp_path.as_uri(),
        batch_size=10,
        read_concurrency=1,
    )
    assert isinstance(provider, LocalStorageProvider)
    assert provider.root_path == tmp_path


def test_factory_uses_local_path(tmp_path) -> None:
    provider = create_storage_provider(
        source_uri=str(tmp_path / "cache"),
        batch_size=10,
        read_concurrency=1,
    )
    assert isinstance(provider, LocalStorageProvider)
    assert (tmp_path / "cache").is_dir()


def test_factory_azure_requires_connection_string() -> None:
    with pytest.raises(ValueError, match="connection string"):
        create_storage_provider(
            source_uri="azure://https://account.blob.core.windows.net/xtra",
            batch_size=10,
            read_concurrency=1,
        )


def test_factory_rejects_http_uri() -> None:
    with pytest.raises(ValueError, match="Unsupported storage URI"):
        create_storage_provider(
            source_uri="https://example.edu/not-storage",
            batch_size=10,
            read_concurrency=1,
        )
