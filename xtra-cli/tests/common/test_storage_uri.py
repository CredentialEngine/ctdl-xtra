from __future__ import annotations

from pathlib import Path

from common.storage_uri import (
    join_storage_uri,
    normalize_storage_uri,
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


def test_normalize_reads_a_portal_container_url_as_azure() -> None:
    """The container URL the Azure portal shows, as people paste it."""
    uri = normalize_storage_uri(
        "https://ceteststorage.blob.core.windows.net/xtra-cli-output"
    )
    assert uri == (
        "azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output"
    )
    parsed = parse_azure_storage_uri(uri)
    assert parsed.container_name == "xtra-cli-output"
    assert parsed.prefix_path == ""


def test_normalize_keeps_the_prefix_path() -> None:
    parsed = parse_azure_storage_uri(
        normalize_storage_uri(
            "https://account.blob.core.windows.net/xtra/catalogs/"
        )
    )
    assert parsed.container_name == "xtra"
    assert parsed.prefix_path == "catalogs"


def test_normalize_leaves_every_other_uri_alone() -> None:
    for uri in (
        "azure://https://account.blob.core.windows.net/xtra",
        "azure://http://127.0.0.1:10000/devstoreaccount1/xtra",
        "https://example.edu/not-storage",
        "https://blob.core.windows.net.example.com/xtra",
        "file:///tmp/xtra",
        "./xtra-cache",
        "",
    ):
        assert normalize_storage_uri(uri) == uri


def test_parse_file_uri(tmp_path) -> None:
    """The URI form keeps forward slashes, which Windows accepts as a path."""
    parsed = parse_file_storage_uri(tmp_path.as_uri())
    assert Path(parsed.local_path) == tmp_path


def test_join_storage_uri() -> None:
    assert (
        join_storage_uri("file:///tmp/xtra", "example", "2026-09-14T18:12:00Z")
        == "file:///tmp/xtra/example/2026-09-14T18:12:00Z"
    )
