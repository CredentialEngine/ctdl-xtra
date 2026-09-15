from __future__ import annotations

from common.storage_uri import (
    join_storage_uri,
    parse_azure_storage_uri,
    parse_file_storage_uri,
)


def test_parse_production_azure_uri() -> None:
    parsed = parse_azure_storage_uri(
        "azure://https://account.blob.core.windows.net/xtra/catalogs"
    )
    assert parsed.container_name == "xtra"
    assert parsed.prefix_path == "catalogs"


def test_parse_azurite_uri() -> None:
    parsed = parse_azure_storage_uri(
        "azure://http://127.0.0.1:10000/devstoreaccount1/xtra/catalogs"
    )
    assert parsed.container_name == "xtra"
    assert parsed.prefix_path == "catalogs"


def test_parse_file_uri(tmp_path) -> None:
    parsed = parse_file_storage_uri(tmp_path.as_uri())
    assert parsed.local_path == str(tmp_path)


def test_join_storage_uri() -> None:
    assert (
        join_storage_uri("file:///tmp/xtra", "example", "2026-09-14T18:12:00Z")
        == "file:///tmp/xtra/example/2026-09-14T18:12:00Z"
    )
