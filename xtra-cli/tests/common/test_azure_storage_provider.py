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
