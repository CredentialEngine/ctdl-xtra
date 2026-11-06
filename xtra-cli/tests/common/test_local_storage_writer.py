from __future__ import annotations

import pytest

from common.local_storage_writer import LocalStorageWriter


def test_upload_text_and_bytes(tmp_path) -> None:
    writer = LocalStorageWriter(root_path=str(tmp_path), write_concurrency=2)
    errors: list[str] = []
    uploaded = writer.upload_batch(
        key_contents={
            "a/b.txt": "hello",
            "a/c.bin": b"bytes",
        },
        content_type="text/plain",
        errors=errors,
    )
    assert not errors
    assert set(uploaded) == {"a/b.txt", "a/c.bin"}
    assert (tmp_path / "a" / "b.txt").read_text(encoding="utf-8") == "hello"
    assert (tmp_path / "a" / "c.bin").read_bytes() == b"bytes"


def test_open_binary_writer_and_delete(tmp_path) -> None:
    writer = LocalStorageWriter(root_path=str(tmp_path), write_concurrency=1)
    with writer.open_binary_writer(
        key="run/page.html", content_type="text/html"
    ) as stream:
        stream.write(b"<html/>")
    assert (tmp_path / "run" / "page.html").read_bytes() == b"<html/>"
    errors: list[str] = []
    deleted = writer.delete_batch(keys=["run/page.html"], errors=errors)
    assert deleted == ["run/page.html"]
    assert not (tmp_path / "run" / "page.html").exists()
    assert str(tmp_path) == writer.describe_location()


def test_upload_new_writes_an_object_that_was_not_there(tmp_path) -> None:
    writer = LocalStorageWriter(root_path=str(tmp_path), write_concurrency=1)
    key = writer.upload_new(
        key="run/manifest.json", content="{}", content_type="application/json"
    )
    assert key == "run/manifest.json"
    written = tmp_path / "run" / "manifest.json"
    assert written.read_text(encoding="utf-8") == "{}"


def test_upload_new_refuses_an_object_that_exists_and_keeps_it(
    tmp_path,
) -> None:
    writer = LocalStorageWriter(root_path=str(tmp_path), write_concurrency=1)
    writer.upload_new(
        key="run/a.json", content="first", content_type="text/plain"
    )
    with pytest.raises(FileExistsError, match="run/a.json"):
        writer.upload_new(
            key="run/a.json", content="second", content_type="text/plain"
        )
    assert (tmp_path / "run" / "a.json").read_text(encoding="utf-8") == "first"


def test_upload_new_writes_bytes_as_given(tmp_path) -> None:
    writer = LocalStorageWriter(root_path=str(tmp_path), write_concurrency=1)
    writer.upload_new(
        key="run/page.html", content=b"<html/>", content_type="text/html"
    )
    assert (tmp_path / "run" / "page.html").read_bytes() == b"<html/>"


def test_upload_new_writes_only_the_object_itself(tmp_path) -> None:
    """No staging folder, no temporary files beside it."""
    writer = LocalStorageWriter(root_path=str(tmp_path), write_concurrency=1)
    writer.upload_new(key="run/a.json", content="x", content_type="text/plain")
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert files == [tmp_path / "run" / "a.json"]


def test_the_staging_folder_is_gone() -> None:
    from common import local_storage_writer

    assert not hasattr(local_storage_writer, "WRITE_ONCE_STAGING_DIR")
