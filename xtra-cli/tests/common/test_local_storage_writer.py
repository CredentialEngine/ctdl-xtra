from __future__ import annotations

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
    with writer.open_binary_writer(key="run/page.html", content_type="text/html") as stream:
        stream.write(b"<html/>")
    assert (tmp_path / "run" / "page.html").read_bytes() == b"<html/>"
    errors: list[str] = []
    deleted = writer.delete_batch(keys=["run/page.html"], errors=errors)
    assert deleted == ["run/page.html"]
    assert not (tmp_path / "run" / "page.html").exists()
    assert str(tmp_path) == writer.describe_location()
