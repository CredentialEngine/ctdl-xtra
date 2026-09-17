from __future__ import annotations

from collections.abc import Iterator

import pytest

from common.object_store import ObjectStore, open_store

RUN = "example/2026-09-14T18-12-00Z"


def test_local_object_store_roundtrip(tmp_path) -> None:
    store = open_store(str(tmp_path / "cache"))
    store.put_json(f"{RUN}/crawl.json", {"pages_saved": 1})
    assert store.get_json(f"{RUN}/crawl.json") == {"pages_saved": 1}
    keys = store.list_keys(under=RUN)
    assert f"{RUN}/crawl.json" in keys
    assert store.exists(f"{RUN}/crawl.json")
    assert not store.exists("missing.json")
    with pytest.raises(FileNotFoundError):
        store.get_bytes("missing.json")
    assert "cache" in store.describe_location()


class _NeverDownloads:
    """A provider whose download path fails the test if it is used."""

    prefix_path = "catalogs"

    def __init__(self, present: set[str], error: Exception | None = None) -> None:
        self.present = present
        self.error = error
        self.listed: list[str | None] = []

    def exists(self, key: str) -> bool:
        if self.error is not None:
            raise self.error
        return key in self.present

    def load_batch(self, *, keys, errors):
        raise AssertionError("exists must not download the object")

    def iter_keys(self, *, name_starts_with: str | None = None) -> Iterator[str]:
        self.listed.append(name_starts_with)
        yield from sorted(self.present)


def test_exists_asks_the_provider_and_never_downloads() -> None:
    provider = _NeverDownloads({"catalogs/example/pages/a.html"})
    store = ObjectStore(provider=provider, writer=None)
    assert store.exists("example/pages/a.html")
    assert not store.exists("example/pages/b.html")


def test_exists_raises_when_the_store_itself_is_broken() -> None:
    provider = _NeverDownloads(set(), error=RuntimeError("credential expired"))
    store = ObjectStore(provider=provider, writer=None)
    with pytest.raises(RuntimeError, match="credential expired"):
        store.exists("example/pages/a.html")


def test_list_keys_hands_the_prefix_to_the_provider() -> None:
    provider = _NeverDownloads(
        {
            "catalogs/example/run/crawl.json",
            "catalogs/example/run/pages/a.html",
            "catalogs/other/run/crawl.json",
        }
    )
    store = ObjectStore(provider=provider, writer=None)
    keys = store.list_keys(under="example/run")
    assert provider.listed == ["catalogs/example/run"]
    assert keys == ["example/run/crawl.json", "example/run/pages/a.html"]


def test_list_keys_without_a_needle_uses_the_whole_prefix() -> None:
    provider = _NeverDownloads({"catalogs/example/run/crawl.json"})
    store = ObjectStore(provider=provider, writer=None)
    assert store.list_keys() == ["example/run/crawl.json"]
    assert provider.listed == ["catalogs"]


def test_azure_listing_is_narrowed_by_the_container_client(monkeypatch) -> None:
    """The prefix reaches Azure, so one run is not a whole-container scan."""
    pytest.importorskip("azure.storage.blob")
    from common.azure_storage_provider import AzureBlobStorageProvider
    from common.storage_configuration import AzureStorageConfiguration

    asked: list[str] = []

    class FakeBlob:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakeContainer:
        def list_blobs(self, *, name_starts_with):
            asked.append(name_starts_with)
            return [FakeBlob("catalogs/example/run/crawl.json")]

    class FakeService:
        def get_container_client(self, container_name):
            return FakeContainer()

    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.from_connection_string",
        lambda connection_string: FakeService(),
    )
    provider = AzureBlobStorageProvider(
        container_name="xtra",
        prefix_path="catalogs",
        batch_size=100,
        read_concurrency=1,
        azure_configuration=AzureStorageConfiguration(
            connection_string="UseDevelopmentStorage=true"
        ),
    )
    store = ObjectStore(provider=provider, writer=None)
    assert store.list_keys(under="example/run") == ["example/run/crawl.json"]
    assert asked == ["catalogs/example/run"]
