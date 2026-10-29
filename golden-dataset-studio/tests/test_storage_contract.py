"""One contract, three backends: a local folder (always), Azurite and the Azure scratch prefix (marked `azure`).

    uv run pytest tests/test_storage_contract.py                     # local only
    uv run pytest -m azure tests/test_storage_contract.py            # + Azurite (127.0.0.1:10000) + Azure scratch

The Azure scratch backend needs AZURE_STORAGE_CONNECTION_STRING and writes only under
xtra-cli-output/zz-scratch-review-ui-v3/test-<random>/, which it deletes afterwards.
"""

from __future__ import annotations

import os
import socket
import threading
import uuid

import pytest

from golden_datasets import manifest
from golden_datasets.errors import ConflictError
from golden_datasets.log import AnnotationLog, new_id
from golden_datasets.storage import AzureRoot, LocalRoot, open_root
from golden_datasets.sync import sync_catalog

SCRATCH = "azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output/zz-scratch-review-ui-v3"


def _azurite_up() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", 10000)) == 0


def _azurite_root():
    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import BlobServiceClient

    from golden_datasets.storage import AZURITE_CONNECTION

    svc = BlobServiceClient.from_connection_string(AZURITE_CONNECTION)
    try:
        svc.create_container("contract")
    except ResourceExistsError:
        pass
    return open_root(f"azure://http://127.0.0.1:10000/devstoreaccount1/contract/run-{uuid.uuid4().hex[:8]}")


def _scratch_root():
    return open_root(f"{SCRATCH}/test-{uuid.uuid4().hex[:8]}")


@pytest.fixture(params=[
    "local",
    pytest.param("azurite", marks=pytest.mark.azure),
    pytest.param("scratch", marks=pytest.mark.azure),
])
def root(request, tmp_path, monkeypatch):
    monkeypatch.setenv("GOLDEN_DATASETS_CACHE", str(tmp_path / "cache"))
    if request.param == "local":
        yield LocalRoot(tmp_path / "root")
        return
    if request.param == "azurite":
        if not _azurite_up():
            pytest.skip("Azurite is not running on 127.0.0.1:10000")
        r = _azurite_root()
    else:
        if not os.environ.get("AZURE_STORAGE_CONNECTION_STRING"):
            pytest.skip("AZURE_STORAGE_CONNECTION_STRING is not set")
        r = _scratch_root()
    yield r
    for p in r.list(""):
        r.delete(p)


def test_write_read_exists(root):
    assert not root.exists("a/b.json")
    etag = root.write_json("a/b.json", {"x": 1})
    assert etag and root.exists("a/b.json")
    assert root.read_json("a/b.json") == {"x": 1}
    assert root.stat("a/b.json").size == len(root.read_bytes("a/b.json"))
    with pytest.raises(FileNotFoundError):
        root.read_bytes("a/missing.json")


def test_if_none_match_refuses_overwrite(root):
    root.write_text("imm/v0001.json", "one", if_none_match=True)
    with pytest.raises(ConflictError):
        root.write_text("imm/v0001.json", "two", if_none_match=True)
    assert root.read_text("imm/v0001.json") == "one"


def test_if_match_refuses_stale_etag(root):
    e1 = root.write_text("m.json", "1")
    e2 = root.write_text("m.json", "2", if_match=e1)
    assert e2 != e1
    with pytest.raises(ConflictError):
        root.write_text("m.json", "3", if_match=e1)
    assert root.read_text("m.json") == "2"


def test_append_and_incremental_read(root):
    log = AnnotationLog(root, "cat/golden-dataset-studio/annotations.jsonl")
    assert log.events() == []
    ev = {"annotation_id": new_id(), "type": "verdict", "at": "2026-10-26T00:00:00Z", "author": "Jared",
          "target": {"kind": "match", "rule_id": "r"}, "verdict": "correct"}
    log.append(ev)
    log.append({**ev, "annotation_id": new_id()})
    assert len(log.events()) == 2
    first_offset = log.offset
    # A second reader appends; the first reads only the new bytes.
    other = AnnotationLog(root, log.path)
    other.append({**ev, "annotation_id": new_id(), "verdict": "wrong"})
    assert log.refresh() == 1
    assert log.offset > first_offset
    assert [e["verdict"] for e in log.events()] == ["correct", "correct", "wrong"]
    assert root.read_from(log.path, log.offset) == b""


def test_log_rejects_bad_events(root):
    log = AnnotationLog(root, "x.jsonl")
    with pytest.raises(ValueError):
        log.append({"annotation_id": "a", "type": "verdict", "at": "t", "author": "J",
                    "target": {"kind": "match"}, "verdict": "missing"})  # missing is for locators/page rules


def test_local_path_caches_immutable_files(root):
    root.write_text("rules/r/v0001.json", "{}")
    p1 = root.local_path("rules/r/v0001.json")
    assert p1.read_text() == "{}"
    if isinstance(root, AzureRoot):
        root.write_text("rules/r/v0001.json", "changed")  # never happens to an immutable file; proves the cache
        assert root.local_path("rules/r/v0001.json").read_text() == "{}"
        assert root.local_path("rules/r/v0001.json", mutable=True).read_text() == "changed"


def test_manifest_update_is_atomic_under_concurrency(root):
    def add(i):
        manifest.update(root, lambda doc: doc.setdefault("items", []).append(i))

    threads = [threading.Thread(target=add, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    doc, etag = manifest.load(root)
    assert sorted(doc["items"]) == list(range(6)) and etag


def test_list_and_list_dirs(root):
    for p in ("c/2026/pages/a.html", "c/2026/pages/b.html", "c/2026/crawl.json", "c/golden-dataset-studio/x.json"):
        root.write_text(p, "x")
    assert root.list("c/2026/pages") == ["c/2026/pages/a.html", "c/2026/pages/b.html"]
    assert root.list_dirs("c") == ["2026", "golden-dataset-studio"]
    assert root.sizes("c/2026")["c/2026/crawl.json"] == 1


def _fake_crawl(r, catalog="cat", crawl="2026-10-01T00-00-00Z"):
    r.write_text(f"{catalog}/{crawl}/crawl.json", "{}")
    r.write_text(f"{catalog}/{crawl}/pages/p1.html", "<html></html>")
    r.write_text(f"{catalog}/{crawl}/pages/p1.meta.json", "{}")
    r.write_text(f"{catalog}/golden-dataset-studio/rules/r/v0001.json", "{}")
    r.append(f"{catalog}/golden-dataset-studio/annotations.jsonl", b'{"a":1}\n')
    manifest.update(r, lambda doc: doc["catalogs"].append(
        {"catalog": catalog, "name": catalog, "crawls": [{"crawl": crawl}], "current_crawl": crawl}))


def test_sync_both_directions(root, tmp_path):
    local = LocalRoot(tmp_path / "local")
    _fake_crawl(local)
    stats = sync_catalog(local, root, "cat", None, "copy", False, False)
    assert stats["pages_total"] == 2 and root.read_text("cat/2026-10-01T00-00-00Z/pages/p1.html") == "<html></html>"
    assert manifest.load(root)[0]["catalogs"][0]["catalog"] == "cat"
    # Append on the target, then sync back: the log is appended, never overwritten.
    root.append("cat/golden-dataset-studio/annotations.jsonl", b'{"a":2}\n')
    back = sync_catalog(root, local, "cat", None, "skip", False, False)
    assert back["annotations"].startswith("appended")
    assert local.read_text("cat/golden-dataset-studio/annotations.jsonl") == '{"a":1}\n{"a":2}\n'
    again = sync_catalog(local, root, "cat", None, "copy", False, False)
    assert again["studio_files"] == 0 and again["pages_to_copy"] == 0


def test_sync_link_pages(tmp_path):
    src, dst = LocalRoot(tmp_path / "src"), LocalRoot(tmp_path / "dst")
    _fake_crawl(src)
    sync_catalog(src, dst, "cat", None, "link", False, False)
    assert (dst.base / "cat/2026-10-01T00-00-00Z/pages").is_symlink()
    assert dst.read_text("cat/2026-10-01T00-00-00Z/pages/p1.html") == "<html></html>"
