"""One set of storage tests, run against the local folder store and Azure (Azurite)."""

import threading

import pytest

from review_ui.store import LocalStore, open_store


@pytest.fixture(params=["local", "azure"])
def store(request, tmp_path):
    if request.param == "local":
        return LocalStore(tmp_path)
    container = request.getfixturevalue("azure_container")
    return open_store(
        container[1], cache=False
    )  # the Azure store itself, not the cache


def test_text_and_json_round_trip_and_overwrite(store):
    store.write_text("a/b.txt", "héllo")
    assert store.read_text("a/b.txt") == "héllo"
    store.write_json("a/c.json", {"x": [1, 2]})
    store.write_json("a/c.json", {"x": [3]})
    assert store.read_json("a/c.json") == {"x": [3]}


def test_reading_a_missing_file_is_file_not_found(store):
    with pytest.raises(FileNotFoundError):
        store.read_text("nope.txt")
    with pytest.raises(FileNotFoundError):
        store.read_json("nope.json")


def test_append_jsonl_creates_then_accumulates_in_order(store):
    assert store.read_jsonl("log/e.jsonl") == []
    for n in range(5):
        store.append_jsonl("log/e.jsonl", {"n": n, "t": "é"})
    assert [e["n"] for e in store.read_jsonl("log/e.jsonl")] == [0, 1, 2, 3, 4]


def test_concurrent_appends_lose_nothing(store):
    threads = [
        threading.Thread(target=lambda n=n: store.append_jsonl("e.jsonl", {"n": n}))
        for n in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(e["n"] for e in store.read_jsonl("e.jsonl")) == list(range(20))


def test_exists_is_for_files(store):
    store.write_text("d/f.txt", "")
    assert store.exists("d/f.txt") and not store.exists("d/g.txt")


def test_list_dir_names_files_and_folders_once(store):
    store.write_text("d/b.txt", "")
    store.write_text("d/a.txt", "")
    store.write_text("d/sub/x.txt", "")
    store.write_text("d/sub/y.txt", "")
    assert store.list_dir("d") == ["a.txt", "b.txt", "sub"]
    assert store.list_dir("missing") == []


def test_list_dir_of_the_root(store):
    store.write_text("one/x.txt", "")
    store.write_text("two.txt", "")
    assert store.list_dir("") == ["one", "two.txt"]


def test_keys_cannot_escape_the_root(store):
    with pytest.raises(ValueError):
        store.write_text("../evil.txt", "x")
    with pytest.raises(ValueError):
        store.read_text("a/../../evil.txt")


def test_find_files_returns_folders_holding_the_file_and_does_not_descend(store):
    store.write_text("catalog/catalog/run1/crawl.json", "{}")
    store.write_text(
        "catalog/catalog/run1/pages/crawl.json", "{}"
    )  # inside a run: ignored
    store.write_text("catalog/catalog/run2/crawl.json", "{}")
    store.write_text("flat/crawl.json", "{}")
    store.write_text("other/notes.txt", "")
    assert store.find_files("crawl.json") == [
        "catalog/catalog/run1",
        "catalog/catalog/run2",
        "flat",
    ]


def test_find_files_respects_depth_and_skips_tooling_folders(store):
    store.write_text("a/b/c/d/e/crawl.json", "{}")  # five levels down
    store.write_text("node_modules/x/crawl.json", "{}")
    store.write_text("review-ui-index/crawl.json", "{}")
    assert store.find_files("crawl.json", max_depth=4) == []
    assert store.find_files("crawl.json", max_depth=5) == ["a/b/c/d/e"]


def test_find_files_at_the_root(store):
    store.write_text("crawl.json", "{}")
    assert store.find_files("crawl.json") == [""]


def test_update_json_creates_then_updates_and_returns_the_new_value(store):
    first = store.update_json("idx.json", lambda cur: cur + [1], default=[])
    second = store.update_json("idx.json", lambda cur: cur + [2], default=[])
    assert (first, second) == ([1], [1, 2]) and store.read_json("idx.json") == [1, 2]


def test_concurrent_updates_lose_nothing(store):
    threads = [
        threading.Thread(
            target=lambda n=n: store.update_json(
                "idx.json", lambda cur: cur + [n], default=[]
            )
        )
        for n in range(16)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(store.read_json("idx.json")) == list(range(16))


def test_location_says_where_the_file_lives(store, request):
    where = store.location("a/b.json")
    assert where.endswith("a/b.json")
    if "azure" in request.node.callspec.id:
        assert where.startswith("azure://http://127.0.0.1:10000/devstoreaccount1/")


def test_open_store_returns_an_existing_store_unchanged(tmp_path):
    local = LocalStore(tmp_path)
    assert open_store(local) is local
    assert isinstance(open_store(str(tmp_path)), LocalStore)
