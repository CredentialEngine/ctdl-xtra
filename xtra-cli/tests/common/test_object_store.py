from __future__ import annotations

from collections.abc import Iterator

import pytest

from common.models import DownloadedResource
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

    def __init__(
        self, present: set[str], error: Exception | None = None
    ) -> None:
        self.present = present
        self.error = error
        self.listed: list[str | None] = []

    def exists(self, key: str) -> bool:
        if self.error is not None:
            raise self.error
        return key in self.present

    def load_batch(self, *, keys, errors):
        raise AssertionError("exists must not download the object")

    def iter_keys(
        self, *, name_starts_with: str | None = None
    ) -> Iterator[str]:
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


class _Batches:
    """A provider that records every batch it is handed."""

    def __init__(
        self, objects: dict[str, bytes], prefix_path: str = ""
    ) -> None:
        self.objects = objects
        self.prefix_path = prefix_path
        self.batches: list[list[str]] = []

    def load_batch(self, *, keys, errors):
        self.batches.append(list(keys))
        found = []
        for key in keys:
            if key in self.objects:
                found.append(
                    DownloadedResource(key=key, content=self.objects[key])
                )
            else:
                errors.append(f"{key}: not found")
        return found


def test_get_many_returns_each_object_in_the_order_asked(tmp_path) -> None:
    store = open_store(str(tmp_path / "cache"))
    for name in ("a", "b", "c"):
        store.put_text(f"{RUN}/{name}.txt", name.upper())
    assert store.get_many([f"{RUN}/c.txt", f"{RUN}/a.txt"]) == [b"C", b"A"]
    assert store.get_many([]) == []


def test_get_many_hands_the_whole_batch_to_the_provider_at_once() -> None:
    """One call per batch is what lets Azure download it in parallel."""
    provider = _Batches({"a": b"1", "b": b"2", "c": b"3"})
    store = ObjectStore(provider=provider, writer=None)
    assert store.get_many(["a", "b", "c"]) == [b"1", b"2", b"3"]
    assert provider.batches == [["a", "b", "c"]]


def test_get_many_falls_back_to_the_bare_key_like_get_bytes() -> None:
    provider = _Batches(
        {"runs/a": b"prefixed", "b": b"bare"}, prefix_path="runs"
    )
    store = ObjectStore(provider=provider, writer=None)
    assert store.get_many(["a", "b"]) == [b"prefixed", b"bare"]
    assert provider.batches == [["runs/a", "runs/b"], ["b"]]


def test_get_many_names_what_it_could_not_read() -> None:
    store = ObjectStore(provider=_Batches({"a": b"1"}), writer=None)
    with pytest.raises(FileNotFoundError, match=r"1 of 2 .*first b \(b: "):
        store.get_many(["a", "b"])


def test_delete_removes_objects_and_leaves_the_rest(tmp_path) -> None:
    store = open_store(str(tmp_path / "cache"))
    for name in ("a", "b", "c"):
        store.put_text(f"{RUN}/{name}.txt", name)
    store.delete([f"{RUN}/a.txt", f"{RUN}/b.txt"])
    assert store.list_keys(under=RUN) == [f"{RUN}/c.txt"]


def test_a_delete_that_fails_is_raised() -> None:
    class Refusing:
        def delete_batch(self, *, keys, errors):
            errors.append(f"{keys[0]}: denied")
            return []

    store = ObjectStore(provider=None, writer=Refusing())
    with pytest.raises(RuntimeError, match="a: denied"):
        store.delete(["a"])
