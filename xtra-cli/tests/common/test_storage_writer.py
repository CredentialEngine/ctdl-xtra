from __future__ import annotations

from common.local_storage_writer import LocalStorageWriter
from common.storage_writer import StorageWriter


def test_storage_writer_protocol_lists_upload_methods() -> None:
    names = set(dir(StorageWriter))
    for method in (
        "upload_batch",
        "open_binary_writer",
        "delete_batch",
        "describe_location",
    ):
        assert method in names


def test_local_writer_matches_protocol_shape(tmp_path) -> None:
    writer = LocalStorageWriter(root_path=str(tmp_path), write_concurrency=1)
    for method in (
        "upload_batch",
        "open_binary_writer",
        "delete_batch",
        "describe_location",
    ):
        assert callable(getattr(writer, method))
