import pytest

from review_ui.store import LocalStore


def test_json_round_trip_creates_parent_dirs(tmp_path):
    store = LocalStore(tmp_path)
    store.write_json("a/b/c.json", {"x": [1, 2]})
    assert store.read_json("a/b/c.json") == {"x": [1, 2]}


def test_write_leaves_no_temp_files(tmp_path):
    store = LocalStore(tmp_path)
    store.write_text("f.txt", "hi")
    assert [p.name for p in tmp_path.iterdir()] == ["f.txt"]


def test_append_jsonl_accumulates_and_reads_back_in_order(tmp_path):
    store = LocalStore(tmp_path)
    store.append_jsonl("e.jsonl", {"n": 1})
    store.append_jsonl("e.jsonl", {"n": 2})
    assert store.read_jsonl("e.jsonl") == [{"n": 1}, {"n": 2}]


def test_missing_jsonl_reads_as_empty(tmp_path):
    assert LocalStore(tmp_path).read_jsonl("nope.jsonl") == []


def test_keys_cannot_escape_the_root(tmp_path):
    with pytest.raises(ValueError):
        LocalStore(tmp_path / "root").write_text("../evil.txt", "x")


def test_list_dir_and_exists(tmp_path):
    store = LocalStore(tmp_path)
    store.write_text("d/b.txt", "")
    store.write_text("d/a.txt", "")
    assert store.list_dir("d") == ["a.txt", "b.txt"]
    assert store.list_dir("missing") == []
    assert store.exists("d/a.txt") and not store.exists("d/z.txt")
