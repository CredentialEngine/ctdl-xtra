from __future__ import annotations

import os

import pytest

from common.object_store import open_store

AZURITE_URI = (
    "azure://http://127.0.0.1:10000/devstoreaccount1/xtra-cli-test"
)

azure_blob = pytest.importorskip("azure.storage.blob")

from common.azure_storage_writer import AzureBlobStorageWriter


class FakeBlobClient:
    def __init__(self) -> None:
        self.uploads: list[tuple] = []
        self.deleted: list[str] = []

    def upload_blob(self, content, overwrite, content_settings) -> None:
        self.uploads.append((content, overwrite, content_settings.content_type))

    def delete_blob(self) -> None:
        return None


class FakeContainer:
    def __init__(self) -> None:
        self.created = False
        self.clients: dict[str, FakeBlobClient] = {}

    def create_container(self) -> None:
        self.created = True

    def get_blob_client(self, key: str) -> FakeBlobClient:
        self.clients[key] = FakeBlobClient()
        return self.clients[key]

    def delete_blob(self, key: str) -> None:
        self.clients.pop(key, None)


class FakeService:
    def __init__(self) -> None:
        self.container = FakeContainer()

    def get_container_client(self, container_name: str) -> FakeContainer:
        return self.container


def test_writer_upload_and_delete_with_prefix(monkeypatch) -> None:
    service = FakeService()
    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.from_connection_string",
        lambda connection_string: service,
    )
    writer = AzureBlobStorageWriter(
        container_name="xtra",
        prefix_path="catalogs",
        write_concurrency=1,
        connection_string="UseDevelopmentStorage=true",
    )
    errors: list[str] = []
    uploaded = writer.upload_batch(
        key_contents={"example/slots.json": "{}"},
        content_type="application/json",
        errors=errors,
    )
    assert not errors
    assert uploaded == ["catalogs/example/slots.json"]
    assert "catalogs/example/slots.json" in service.container.clients
    deleted = writer.delete_batch(keys=["example/slots.json"], errors=errors)
    assert deleted == ["catalogs/example/slots.json"]
    assert writer.describe_location() == "azure://xtra/catalogs"


def test_writer_requires_connection_string(monkeypatch) -> None:
    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.from_connection_string",
        lambda connection_string: FakeService(),
    )
    with pytest.raises(ValueError, match="connection string"):
        AzureBlobStorageWriter(
            container_name="xtra",
            prefix_path="",
            write_concurrency=1,
            connection_string="",
        )


@pytest.mark.integration
def test_azurite_roundtrip() -> None:
    connection = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection:
        pytest.skip("Set AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true")
    store = open_store(
        AZURITE_URI,
        azure_storage_connection_string=connection,
    )
    key = "example/2026-09-14T18:12:00Z/crawl.json"
    store.put_json(key, {"ok": True})
    assert store.get_json(key) == {"ok": True}
