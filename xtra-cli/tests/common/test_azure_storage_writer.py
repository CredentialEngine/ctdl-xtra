from __future__ import annotations

import os

import pytest

from common.object_store import open_store

AZURITE_URI = "azure://http://127.0.0.1:10000/devstoreaccount1/xtra-cli-test"

azure_blob = pytest.importorskip("azure.storage.blob")

from common.azure_storage_writer import (
    AzureBlobStorageWriter,
    AzureBlobUploadWriter,
)


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


class FakeBlockBlobClient:
    def __init__(self) -> None:
        self.staged: list[tuple[str, bytes]] = []
        self.committed: tuple[list[str], str] | None = None

    def stage_block(self, block_id, data) -> None:
        self.staged.append((block_id, data))

    def commit_block_list(self, block_list, content_settings) -> None:
        self.committed = (list(block_list), content_settings.content_type)


def _writer(monkeypatch, service, *, prefix_path="catalogs"):
    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.from_connection_string",
        lambda connection_string: service,
    )
    return AzureBlobStorageWriter(
        container_name="xtra",
        prefix_path=prefix_path,
        write_concurrency=1,
        connection_string="UseDevelopmentStorage=true",
    )


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


@pytest.mark.parametrize(
    "refusal", ["ResourceExistsError", "HttpResponseError"]
)
def test_writer_carries_on_when_the_container_cannot_be_created(
    monkeypatch, refusal
) -> None:
    """The container already exists, or the credential may not create one."""
    from azure.core import exceptions

    def refuse() -> None:
        raise getattr(exceptions, refusal)("ContainerAlreadyExists")

    service = FakeService()
    service.container.create_container = refuse
    writer = _writer(monkeypatch, service, prefix_path="")
    assert writer.describe_location() == "azure://xtra"


def test_writer_upload_batch_records_a_failed_upload(monkeypatch) -> None:
    class RejectingBlobClient(FakeBlobClient):
        def upload_blob(self, content, overwrite, content_settings) -> None:
            raise RuntimeError("413 The request body is too large")

    service = FakeService()
    accept = service.container.get_blob_client
    service.container.get_blob_client = lambda key: (
        RejectingBlobClient() if key.endswith("big.json") else accept(key)
    )
    writer = _writer(monkeypatch, service)
    errors: list[str] = []
    uploaded = writer.upload_batch(
        key_contents={"run/a.json": "{}", "run/big.json": "{}"},
        content_type="application/json",
        errors=errors,
    )
    assert uploaded == ["catalogs/run/a.json"]
    assert errors == ["run/big.json: 413 The request body is too large"]


def test_writer_delete_batch_records_a_failed_delete(monkeypatch) -> None:
    def delete_blob(key: str) -> None:
        raise RuntimeError("409 There is currently a lease")

    service = FakeService()
    service.container.delete_blob = delete_blob
    writer = _writer(monkeypatch, service, prefix_path="")
    errors: list[str] = []
    assert writer.delete_batch(keys=["run/a.json"], errors=errors) == []
    assert errors == ["run/a.json: 409 There is currently a lease"]


def test_upload_writer_stages_full_chunks_and_commits_the_rest_once() -> None:
    client = FakeBlockBlobClient()
    writer = AzureBlobUploadWriter(
        blob_client=client, content_type="text/html", chunk_size=4
    )
    assert writer.writable()
    assert writer.write(b"abcdefghij") == 10
    assert client.staged == [("00000000", b"abcd"), ("00000001", b"efgh")]
    assert client.committed is None

    writer.close()
    assert client.staged[-1] == ("00000002", b"ij")
    assert client.committed == (
        ["00000000", "00000001", "00000002"],
        "text/html",
    )

    writer.close()
    assert len(client.staged) == 3
    with pytest.raises(ValueError, match="closed"):
        writer.write(b"k")


def test_open_binary_writer_commits_under_the_prefixed_key(monkeypatch) -> None:
    clients: dict[str, FakeBlockBlobClient] = {}

    def get_blob_client(key: str) -> FakeBlockBlobClient:
        clients[key] = FakeBlockBlobClient()
        return clients[key]

    service = FakeService()
    service.container.get_blob_client = get_blob_client
    writer = _writer(monkeypatch, service, prefix_path="catalogs/")
    with writer.open_binary_writer(
        key="/run/pages/a.html", content_type="text/html"
    ) as out:
        out.write(b"<html></html>")

    client = clients["catalogs/run/pages/a.html"]
    assert client.staged == [("00000000", b"<html></html>")]
    assert client.committed == (["00000000"], "text/html")


@pytest.mark.integration
def test_azurite_roundtrip() -> None:
    connection = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection:
        pytest.skip(
            "Set AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true"
        )
    store = open_store(
        AZURITE_URI,
        azure_storage_connection_string=connection,
    )
    key = "example/2026-09-14T18:12:00Z/crawl.json"
    store.put_json(key, {"ok": True})
    assert store.get_json(key) == {"ok": True}
