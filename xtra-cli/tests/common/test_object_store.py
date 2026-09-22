from __future__ import annotations

import pytest

from common.object_store import open_store


def test_local_object_store_roundtrip(tmp_path) -> None:
    store = open_store(str(tmp_path / "cache"))
    store.put_json("example/2026-09-14T18:12:00Z/slots.json", {"slots": [1]})
    payload = store.get_json("example/2026-09-14T18:12:00Z/slots.json")
    assert payload == {"slots": [1]}
    keys = store.list_keys(under="example/2026-09-14T18:12:00Z")
    assert "example/2026-09-14T18:12:00Z/slots.json" in keys
    assert store.exists("example/2026-09-14T18:12:00Z/slots.json")
    assert not store.exists("missing.json")
    with pytest.raises(FileNotFoundError):
        store.get_bytes("missing.json")
    assert "cache" in store.describe_location()
