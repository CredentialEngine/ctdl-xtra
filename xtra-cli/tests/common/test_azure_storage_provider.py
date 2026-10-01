from __future__ import annotations

import pytest

azure_blob = pytest.importorskip("azure.storage.blob")

from common.azure_storage_provider import AzureBlobStorageProvider
from common.storage_configuration import AzureStorageConfiguration


class FakeDownloadedBlob:
    def __init__(self, content) -> None:
        self.content = content

    def readall(self):
        return self.content


class FakeProviderBlobClient:
    def __init__(self, content) -> None:
        self.content = content

    def download_blob(self):
        return FakeDownloadedBlob(self.content)


class FakeBlobItem:
    def __init__(self, name) -> None:
        self.name = name


class FakeDeniedBlobClient:
    def download_blob(self):
        raise RuntimeError("403 This request is not authorized")


def _provider(monkeypatch, container, *, prefix_path="catalogs/"):
    class FakeService:
        def get_container_client(self, container_name):
            return container

    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.from_connection_string",
        lambda connection_string: FakeService(),
    )
    return AzureBlobStorageProvider(
        container_name="xtra",
        prefix_path=prefix_path,
        batch_size=100,
        read_concurrency=2,
        azure_configuration=AzureStorageConfiguration(
            connection_string="UseDevelopmentStorage=true"
        ),
    )


def test_provider_iter_keys(monkeypatch) -> None:
    class FakeContainer:
        def list_blobs(self, *, name_starts_with):
            asked.append(name_starts_with)
            return [
                FakeBlobItem("catalogs/a.json"),
                FakeBlobItem("catalogs/b.json"),
            ]

    asked: list[str] = []

    class FakeService:
        def get_container_client(self, container_name):
            return FakeContainer()

    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.from_connection_string",
        lambda connection_string: FakeService(),
    )

    provider = AzureBlobStorageProvider(
        container_name="xtra",
        prefix_path="catalogs/",
        batch_size=100,
        read_concurrency=2,
        azure_configuration=AzureStorageConfiguration(
            connection_string="UseDevelopmentStorage=true"
        ),
    )
    assert list(provider.iter_keys()) == [
        "catalogs/a.json",
        "catalogs/b.json",
    ]
    assert asked == ["catalogs/"]
    list(provider.iter_keys(name_starts_with="catalogs/run"))
    assert asked[-1] == "catalogs/run"


def test_provider_load_batch_downloads_content(monkeypatch) -> None:
    class FakeContainer:
        def get_blob_client(self, key):
            return FakeProviderBlobClient(b"abc")

    class FakeService:
        def get_container_client(self, container_name):
            return FakeContainer()

    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.from_connection_string",
        lambda connection_string: FakeService(),
    )

    provider = AzureBlobStorageProvider(
        container_name="xtra",
        prefix_path="catalogs/",
        batch_size=100,
        read_concurrency=2,
        azure_configuration=AzureStorageConfiguration(
            connection_string="UseDevelopmentStorage=true"
        ),
    )
    errors: list[str] = []
    rows = provider.load_batch(keys=["catalogs/a.json"], errors=errors)
    assert not errors
    assert rows[0].content == b"abc"


def test_exists_uses_the_blob_client_and_never_downloads(monkeypatch) -> None:
    """Missing means False. A broken credential must not read as missing."""

    class FakeBlobClient:
        def __init__(self, key) -> None:
            self.key = key

        def exists(self):
            if self.key == "boom":
                raise RuntimeError("credential expired")
            return self.key == "catalogs/a.json"

        def download_blob(self):
            raise AssertionError("exists must not download the blob")

    class FakeContainer:
        def get_blob_client(self, key):
            return FakeBlobClient(key)

    class FakeService:
        def get_container_client(self, container_name):
            return FakeContainer()

    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.from_connection_string",
        lambda connection_string: FakeService(),
    )
    provider = AzureBlobStorageProvider(
        container_name="xtra",
        prefix_path="catalogs/",
        batch_size=100,
        read_concurrency=1,
        azure_configuration=AzureStorageConfiguration(
            connection_string="UseDevelopmentStorage=true"
        ),
    )
    assert provider.exists("catalogs/a.json")
    assert not provider.exists("catalogs/b.json")
    with pytest.raises(RuntimeError, match="credential expired"):
        provider.exists("boom")


def test_load_batch_records_a_failed_download_and_keeps_the_rest(
    monkeypatch,
) -> None:
    class FakeContainer:
        def get_blob_client(self, key):
            if key == "catalogs/denied.json":
                return FakeDeniedBlobClient()
            return FakeProviderBlobClient(b"abc")

    provider = _provider(monkeypatch, FakeContainer())
    errors: list[str] = []
    rows = provider.load_batch(
        keys=["catalogs/a.json", "catalogs/denied.json"], errors=errors
    )
    assert [row.key for row in rows] == ["catalogs/a.json"]
    assert errors == [
        "catalogs/denied.json: 403 This request is not authorized"
    ]


def test_load_binary_batch_downloads_bytes_the_same_way(monkeypatch) -> None:
    class FakeContainer:
        def get_blob_client(self, key):
            return FakeProviderBlobClient(b"%PDF-1.7")

    provider = _provider(monkeypatch, FakeContainer())
    errors: list[str] = []
    rows = provider.load_binary_batch(keys=["catalogs/a.pdf"], errors=errors)
    assert not errors
    assert rows[0].content == b"%PDF-1.7"


def test_delete_batch_counts_a_missing_blob_as_deleted(monkeypatch) -> None:
    """Missing is the goal of a delete; any other failure is reported."""
    from azure.core.exceptions import ResourceNotFoundError

    class FakeContainer:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def delete_blob(self, key):
            if key == "catalogs/gone.json":
                raise ResourceNotFoundError("BlobNotFound")
            if key == "catalogs/leased.json":
                raise RuntimeError("409 There is currently a lease")
            self.deleted.append(key)

    container = FakeContainer()
    provider = _provider(monkeypatch, container)
    errors: list[str] = []
    deleted = provider.delete_batch(
        keys=["catalogs/a.json", "catalogs/gone.json", "catalogs/leased.json"],
        errors=errors,
    )
    assert sorted(deleted) == ["catalogs/a.json", "catalogs/gone.json"]
    assert container.deleted == ["catalogs/a.json"]
    assert errors == ["catalogs/leased.json: 409 There is currently a lease"]


def test_describe_location_names_the_container_and_any_prefix(
    monkeypatch,
) -> None:
    assert (
        _provider(monkeypatch, object()).describe_location()
        == "azure://xtra/catalogs/"
    )
    assert (
        _provider(monkeypatch, object(), prefix_path="").describe_location()
        == "azure://xtra"
    )
