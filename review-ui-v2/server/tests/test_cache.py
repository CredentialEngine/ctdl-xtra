import gzip
import os
import threading

import pytest

from review_ui import cli
from review_ui.cache import (
    CachedStore,
    DiskCache,
    cache_enabled,
    cache_max_bytes,
    cache_root,
    cached,
    is_cacheable,
    namespace_of,
    warm,
)
from review_ui.store import LocalStore, open_store

RUN = "cat/cat/2026-01-01T00-00-00Z"
PAGE = f"{RUN}/pages/course_admj.html"
META = f"{RUN}/pages/course_admj.meta.json"


class RemoteStore(LocalStore):
    """A LocalStore that counts reads, standing in for a store reached over a network."""

    def __init__(self, root):
        super().__init__(root)
        self.reads: list[str] = []

    def read_text(self, key):
        self.reads.append(key)
        return super().read_text(key)

    def location(self, key):
        return f"azure://https://fake.blob.core.windows.net/box/{key}"


@pytest.fixture
def remote(crawl_root):
    return RemoteStore(crawl_root)


@pytest.fixture
def store(remote, tmp_path):
    return CachedStore(remote, DiskCache(tmp_path / "cache", "ns", 10 * 1024**3))


# -- what is cacheable -----------------------------------------------------------
@pytest.mark.parametrize(
    "key,expected",
    [
        (PAGE, True),
        (META, True),
        ("pages/x.html", True),
        (f"{RUN}/crawl.json", False),
        (f"{RUN}/review-ui/s/decisions.json", False),
        (f"{RUN}/review-ui/s/events.jsonl", False),
        (f"{RUN}/extractions/e/records/A.json", False),
        ("review-ui-index/index.json", False),
        ("review-ui-index/rulesets/x/rules.json", False),
        (f"{RUN}/pages/sub/deeper.html", False),
        (f"{RUN}/pages/x.txt", False),
    ],
)
def test_only_crawled_pages_and_their_metadata_are_cacheable(key, expected):
    assert is_cacheable(key) is expected


# -- the disk cache ----------------------------------------------------------------
def test_an_entry_round_trips_and_is_stored_gzipped(tmp_path):
    cache = DiskCache(tmp_path, "ns", 10**9)
    text = ("<p>some page</p>" * 2000).encode()
    cache.put("run/pages/a.html", text)
    assert cache.get("run/pages/a.html") == text
    stored = (tmp_path / "ns" / "run" / "pages" / "a.html.gz").read_bytes()
    assert gzip.decompress(stored) == text and len(stored) < len(text) // 5


def test_a_miss_returns_none_and_a_key_cannot_escape(tmp_path):
    cache = DiskCache(tmp_path, "ns", 10**9)
    assert cache.get("nope") is None and not cache.has("nope")
    with pytest.raises(ValueError):
        cache.put("../evil.html", b"x")


def test_a_damaged_entry_is_dropped_and_treated_as_a_miss(tmp_path):
    cache = DiskCache(tmp_path, "ns", 10**9)
    cache.put("a/pages/x.html", b"hello")
    (tmp_path / "ns" / "a" / "pages" / "x.html.gz").write_bytes(b"not gzip at all")
    assert cache.get("a/pages/x.html") is None
    assert not cache.has("a/pages/x.html")


def test_least_recently_used_entries_are_evicted_first(tmp_path):
    cache = DiskCache(tmp_path, "ns", 3500)
    for name in "abc":
        cache.put(name, os.urandom(1000))  # random bytes do not compress: ~1 KB each
    for age, name in enumerate("abc"):  # a oldest, c newest
        os.utime(cache._path(name), (100 + age, 100 + age))
    assert cache.get("a") is not None  # using "a" makes it the newest
    cache.put("d", os.urandom(1000))  # now over the limit
    assert cache.has("a") and cache.has("d")
    assert not cache.has("b")  # the least recently used went first
    assert cache.stats().bytes <= 3500


def test_the_size_limit_covers_every_root_in_the_cache_folder(tmp_path):
    first = DiskCache(tmp_path, "one", 3500)
    second = DiskCache(tmp_path, "two", 3500)
    first.put("a", os.urandom(1200))
    os.utime(first._path("a"), (100, 100))
    second.put("b", os.urandom(1200))
    second.put("c", os.urandom(1200))  # the whole folder is now over the limit
    assert not first.has("a")  # the oldest entry in the folder, though in another root
    assert second.has("b") and second.has("c")


def test_clear_removes_one_prefix_or_everything(tmp_path):
    cache = DiskCache(tmp_path, "ns", 10**9)
    for key in ("r1/pages/a.html", "r1/pages/b.html", "r2/pages/c.html"):
        cache.put(key, b"x")
    assert cache.clear("r1") == 2
    assert cache.has("r2/pages/c.html") and not cache.has("r1/pages/a.html")
    assert cache.clear() == 1 and cache.stats().files == 0


def test_concurrent_writers_of_one_key_leave_one_whole_entry(tmp_path):
    cache = DiskCache(tmp_path, "ns", 10**9)
    payload = os.urandom(50_000)
    threads = [
        threading.Thread(target=lambda: cache.put("r/pages/x.html", payload))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert cache.get("r/pages/x.html") == payload
    assert [p.name for p in (tmp_path / "ns" / "r" / "pages").iterdir()] == [
        "x.html.gz"
    ]


# -- the cached store ----------------------------------------------------------------
def test_a_page_is_fetched_once_then_served_from_disk(store, remote):
    first = store.read_text(PAGE)
    second = store.read_text(PAGE)
    assert first == second == remote.read_text(PAGE)
    assert (
        remote.reads.count(PAGE) == 2
    )  # one from the cache miss, one from this assert
    assert store.cache.has(PAGE)


def test_page_metadata_is_cached_as_json(store, remote):
    assert store.read_json(META)["final_url"].startswith("https://")
    remote.reads.clear()
    assert store.read_json(META)["final_url"].startswith("https://")
    assert remote.reads == []


def test_everything_else_always_goes_to_storage(store, remote):
    store.write_json(f"{RUN}/review-ui/s/decisions.json", {"a": 1})
    assert store.read_json(f"{RUN}/review-ui/s/decisions.json") == {"a": 1}
    store.write_json(f"{RUN}/review-ui/s/decisions.json", {"a": 2})
    assert store.read_json(f"{RUN}/review-ui/s/decisions.json") == {
        "a": 2
    }  # never stale
    store.append_jsonl(f"{RUN}/review-ui/s/events.jsonl", {"n": 1})
    store.append_jsonl(f"{RUN}/review-ui/s/events.jsonl", {"n": 2})
    assert [e["n"] for e in store.read_jsonl(f"{RUN}/review-ui/s/events.jsonl")] == [
        1,
        2,
    ]
    assert store.cache.stats(namespace_only=False).files == 0


def test_a_missing_page_raises_and_is_not_cached(store, remote):
    key = f"{RUN}/pages/later.html"
    with pytest.raises(FileNotFoundError):
        store.read_text(key)
    assert not store.cache.has(key)
    remote.write_text(key, "now it exists")
    assert store.read_text(key) == "now it exists"


def test_writing_a_page_drops_its_cached_copy(store):
    key = f"{RUN}/pages/new.html"
    store.write_text(key, "v1")
    assert store.read_text(key) == "v1"
    store.write_text(key, "v2")
    assert not store.cache.has(key) and store.read_text(key) == "v2"


def test_listing_searching_updating_and_location_pass_through(store, remote):
    assert "course_admj.html" in store.list_dir(f"{RUN}/pages")
    assert store.find_files("crawl.json") == [RUN]
    assert store.update_json("idx.json", lambda cur: cur + [1], default=[]) == [1]
    assert store.location("a.json") == remote.location("a.json")
    assert store.exists(PAGE) and not store.exists(f"{RUN}/pages/zzz.html")


# -- configuration ------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [("0", False), ("off", False), ("No", False), ("1", True), ("yes", True)],
)
def test_the_cache_switch(monkeypatch, value, expected):
    monkeypatch.setenv("REVIEW_UI_CACHE", value)
    assert cache_enabled() is expected


def test_folder_and_size_come_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("REVIEW_UI_CACHE_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("REVIEW_UI_CACHE_MAX_GB", "2.5")
    assert cache_root() == tmp_path / "elsewhere"
    assert cache_max_bytes() == int(2.5 * 1024**3)
    monkeypatch.setenv("REVIEW_UI_CACHE_MAX_GB", "lots")
    assert cache_max_bytes() == 10 * 1024**3


def test_the_default_folder_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("REVIEW_UI_CACHE_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache_root() == tmp_path / "review-ui"


def test_each_storage_root_gets_its_own_cache_namespace():
    one = namespace_of("azure://http://127.0.0.1:10000/devstoreaccount1/box-a/")
    two = namespace_of("azure://http://127.0.0.1:10000/devstoreaccount1/box-b/")
    assert one != two and "/" not in one and ":" not in one


def test_cached_wraps_unless_disabled(remote, monkeypatch):
    assert isinstance(cached(remote), CachedStore)
    assert cached(remote, enabled=False) is remote
    monkeypatch.setenv("REVIEW_UI_CACHE", "0")
    assert cached(remote) is remote


def test_local_folders_are_never_cached(tmp_path):
    assert isinstance(open_store(tmp_path), LocalStore)


def test_azure_roots_are_cached_by_default_and_not_with_the_switch(monkeypatch):
    pytest.importorskip("azure.storage.blob")
    root = "azure://http://127.0.0.1:10000/devstoreaccount1/box"
    assert isinstance(open_store(root), CachedStore)
    assert not isinstance(open_store(root, cache=False), CachedStore)
    monkeypatch.setenv("REVIEW_UI_CACHE", "0")
    assert not isinstance(open_store(root), CachedStore)


# -- warming ----------------------------------------------------------------------
def test_warm_downloads_every_page_once(store, remote):
    seen = []
    result = warm(
        store, RUN, threads=4, progress=lambda done, total: seen.append((done, total))
    )
    assert (result.fetched, result.already_cached, result.failed) == (
        10,
        0,
        0,
    )  # 5 pages + 5 metadata
    assert seen[-1] == (10, 10)
    remote.reads.clear()
    again = warm(store, RUN)
    assert (again.fetched, again.already_cached) == (0, 10) and remote.reads == []


def test_warm_counts_a_page_that_vanished_and_lets_real_errors_through(
    store, remote, monkeypatch
):
    original = remote.read_text

    def vanished(key):
        if key.endswith("course_mixed.html"):
            raise FileNotFoundError(key)
        return original(key)

    monkeypatch.setattr(remote, "read_text", vanished)
    result = warm(store, RUN)
    assert (result.fetched, result.failed) == (9, 1)

    def denied(key):
        raise PermissionError("no role")

    store.cache.clear()
    monkeypatch.setattr(remote, "read_text", denied)
    with pytest.raises(PermissionError):
        warm(store, RUN)


# -- the commands ----------------------------------------------------------------------
@pytest.fixture
def fake_azure(store, monkeypatch):
    """Make the CLI see the cached 'remote' store for any root."""
    monkeypatch.setattr(cli, "open_store", lambda root, cache=None: store)
    return store


def test_cache_status_warm_and_clear(fake_azure, capsys):
    base = ["--root", "azure://x/y/z"]
    assert cli.main(["cache", "status", *base]) == 0
    assert "0 files" in capsys.readouterr().out
    assert cli.main(["cache", "warm", *base, "--run", "cat"]) == 0
    assert "downloaded 10, already cached 0" in capsys.readouterr().out
    assert cli.main(["cache", "status", *base]) == 0
    assert "10 files" in capsys.readouterr().out
    assert cli.main(["cache", "clear", *base, "--run", "cat"]) == 0
    assert "cleared 10 files" in capsys.readouterr().out
    assert fake_azure.cache.stats().files == 0


def test_cache_warm_needs_a_run(fake_azure):
    with pytest.raises(SystemExit, match="--run"):
        cli.main(["cache", "warm", "--root", "azure://x/y/z"])


def test_cache_clear_all_empties_the_whole_cache_folder(tmp_path, capsys):
    DiskCache(cache_root(), "one", 10**9).put("a/pages/x.html", b"x")
    DiskCache(cache_root(), "two", 10**9).put("b/pages/y.html", b"y")
    assert cli.main(["cache", "clear", "--all"]) == 0
    assert "(2 files)" in capsys.readouterr().out
    assert list(cache_root().glob("**/*.gz")) == []


def test_a_local_root_says_no_cache_is_in_use(crawl_root, capsys):
    assert cli.main(["cache", "status", "--root", str(crawl_root)]) == 0
    assert "No page cache is in use" in capsys.readouterr().out


def test_no_cache_switches_the_cache_off_for_the_whole_process(crawl_root, monkeypatch):
    monkeypatch.setenv("REVIEW_UI_CACHE", "1")
    cli.main(["rules", "list", "--root", str(crawl_root), "--no-cache"])
    assert os.environ["REVIEW_UI_CACHE"] == "0"  # worker processes inherit this
