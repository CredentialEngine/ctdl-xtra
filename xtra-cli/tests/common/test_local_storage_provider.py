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


def test_iter_keys_can_be_narrowed_to_one_prefix(tmp_path) -> None:
    root = tmp_path / "cache"
    for rel in ("a/run/one.json", "a/run/two.json", "b/run/three.json"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    provider = LocalStorageProvider(
        root_path=str(root), batch_size=10, read_concurrency=1
    )
    assert sorted(provider.iter_keys(name_starts_with="a/run")) == [
        "a/run/one.json",
        "a/run/two.json",
    ]


def test_exists_is_true_only_for_a_stored_file(tmp_path) -> None:
    root = tmp_path / "cache"
    (root / "a" / "run").mkdir(parents=True)
    (root / "a" / "run" / "one.json").write_text("{}", encoding="utf-8")
    provider = LocalStorageProvider(
        root_path=str(root), batch_size=10, read_concurrency=1
    )
    assert provider.exists("a/run/one.json")
    assert not provider.exists("a/run/missing.json")
    # A folder is not a stored object.
    assert not provider.exists("a/run")
