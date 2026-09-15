from __future__ import annotations

from common.local_storage_provider import LocalStorageProvider


def test_iter_load_and_delete(tmp_path) -> None:
    root = tmp_path / "cache"
    nested = root / "example" / "run"
    nested.mkdir(parents=True)
    (nested / "slots.json").write_text("{}", encoding="utf-8")
    provider = LocalStorageProvider(
        root_path=str(root), batch_size=10, read_concurrency=1
    )
    keys = list(provider.iter_keys())
    assert "example/run/slots.json" in keys
    errors: list[str] = []
    rows = provider.load_batch(keys=["example/run/slots.json"], errors=errors)
    assert not errors
    assert rows[0].content == b"{}"
    binary = provider.load_binary_batch(
        keys=["example/run/slots.json"], errors=errors
    )
    assert binary[0].content == b"{}"
    deleted = provider.delete_batch(keys=["example/run/slots.json"], errors=errors)
    assert deleted == ["example/run/slots.json"]
    assert not (nested / "slots.json").exists()
    assert "cache" in provider.describe_location()


def test_missing_key_records_error(tmp_path) -> None:
    provider = LocalStorageProvider(
        root_path=str(tmp_path), batch_size=10, read_concurrency=1
    )
    errors: list[str] = []
    rows = provider.load_batch(keys=["nope.json"], errors=errors)
    assert rows == []
    assert errors


def test_single_file_root(tmp_path) -> None:
    path = tmp_path / "one.json"
    path.write_text("[]", encoding="utf-8")
    provider = LocalStorageProvider(
        root_path=str(path), batch_size=10, read_concurrency=1
    )
    assert list(provider.iter_keys()) == ["one.json"]
    assert str(path) in provider.describe_location()
