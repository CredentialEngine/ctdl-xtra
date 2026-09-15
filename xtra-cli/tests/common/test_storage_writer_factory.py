from __future__ import annotations

import pytest

from common.local_storage_writer import LocalStorageWriter
from common.storage_writer_factory import create_storage_writer


def test_factory_uses_file_uri(tmp_path) -> None:
    writer = create_storage_writer(
        target_uri=tmp_path.as_uri(),
        write_concurrency=1,
    )
    assert isinstance(writer, LocalStorageWriter)


def test_factory_uses_local_path(tmp_path) -> None:
    writer = create_storage_writer(
        target_uri=str(tmp_path / "out"),
        write_concurrency=2,
    )
    assert isinstance(writer, LocalStorageWriter)
    assert writer.root_path == tmp_path / "out"
    assert writer.write_concurrency == 2


def test_factory_azure_requires_connection_string() -> None:
    with pytest.raises(ValueError, match="connection string"):
        create_storage_writer(
            target_uri="azure://https://account.blob.core.windows.net/xtra",
            write_concurrency=1,
        )


def test_factory_rejects_http_uri() -> None:
    with pytest.raises(ValueError, match="Unsupported storage URI"):
        create_storage_writer(
            target_uri="https://example.edu/not-storage",
            write_concurrency=1,
        )
