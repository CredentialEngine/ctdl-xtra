"""Add a catalog (spec §7.1): the crawled-catalog list, names read from the seed URL, and adding a crawl."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from golden_datasets import crawls, manifest
from golden_datasets.storage import AzureRoot, LocalRoot


def _crawl(base: Path, catalog: str, crawl: str, seed: str, pages: int, status: str = "complete") -> None:
    d = base / catalog / crawl
    (d / "pages").mkdir(parents=True)
    (d / "crawl.json").write_text(json.dumps({
        "seed_url": seed, "status": status, "pages_saved": pages, "started_at": "2026-10-01T00:00:00Z",
        "finished_at": f"{crawl[:10]}T12:00:00Z"}))
    for i in range(pages):
        stem = f"page-{i}"
        html = f"<html><head><title>Course {i}</title></head><body><h1>C {i}</h1></body></html>".encode()
        (d / "pages" / f"{stem}.html").write_bytes(html)
        (d / "pages" / f"{stem}.meta.json").write_text(json.dumps({
            "stem": stem, "requested_url": f"{seed}c/{i}", "final_url": f"{seed}c/{i}", "http_status": 200,
            "retrieved_at": "2026-10-01T00:00:00Z", "bytes": len(html), "sha256": "x"}))


@pytest.fixture
def roots(tmp_path):
    src = tmp_path / "xtra-cli-output"
    _crawl(src, "cuesta-curriqunet-com-catalog-iq-27137", "2026-10-03T10-00-00Z",
           "https://cuesta.curriqunet.com/catalog/iq/27137", 2)
    _crawl(src, "cuesta-curriqunet-com-catalog-iq-27137", "2026-10-21T10-00-00Z",
           "https://cuesta.curriqunet.com/catalog/iq/27137", 3)
    _crawl(src, "catalog-ualr-edu", "2026-10-18T21-05-00Z", "https://catalog.ualr.edu/", 2, "limit_reached")
    _crawl(src, "empty-example-com", "2026-10-22T00-00-00Z", "https://empty.example.com/", 0)
    (src / "zz-scratch" / "some-catalog").mkdir(parents=True)  # the Studio's own prefix: no crawls in it
    dst = tmp_path / "root"
    dst.mkdir()
    return LocalRoot(src), LocalRoot(dst)


def test_names_come_from_the_seed_url_host():
    assert crawls.short_name("https://avc.elumenapp.com/catalog/2026-27/welcome") == "avc"
    assert crawls.short_name("https://catalog.ualr.edu/") == "ualr"
    assert crawls.short_name("https://main.catalogs.rutgers.edu") == "rutgers"
    assert crawls.short_name("https://www.microsoft.com/en-us/microsoft-learn") == "microsoft"
    assert crawls.display_name("x", "https://cuesta.curriqunet.com/catalog") == "Cuesta"
    assert crawls.display_name("x", "https://catalog.ualr.edu/") == "UALR"
    assert crawls.display_name("x", "https://cerritos-public.courseleaf.com/") == "Cerritos-Public"
    assert crawls.display_name("catalog-marshall-edu", "https://catalog.marshall.edu/") == "Marshall"  # configured


def test_crawls_root_is_the_container_above_an_azure_prefix(monkeypatch, tmp_path):
    monkeypatch.delenv(crawls.ENV, raising=False)
    root = AzureRoot.__new__(AzureRoot)
    root.uri, root.prefix = "azure://https://acct.blob.core.windows.net/xtra-cli-output/zz-scratch", "zz-scratch"
    assert crawls.default_crawls_root(root) == "azure://https://acct.blob.core.windows.net/xtra-cli-output"
    assert crawls.default_crawls_root(LocalRoot(tmp_path)) == LocalRoot(tmp_path).uri
    monkeypatch.setenv(crawls.ENV, "/elsewhere")
    assert crawls.default_crawls_root(LocalRoot(tmp_path)) == "/elsewhere"


def test_list_has_one_row_per_catalog_with_its_latest_crawl(roots):
    src, _ = roots
    rows = crawls.list_crawled(src, {"catalog-ualr-edu"})
    by = {r["catalog"]: r for r in rows}
    assert set(by) == {"cuesta-curriqunet-com-catalog-iq-27137", "catalog-ualr-edu", "empty-example-com"}
    c = by["cuesta-curriqunet-com-catalog-iq-27137"]
    assert (c["name"], c["crawl"], c["pages"], c["status"]) == ("Cuesta", "2026-10-21T10-00-00Z", 3, "complete")
    assert [k["crawl"] for k in c["crawls"]] == ["2026-10-21T10-00-00Z", "2026-10-03T10-00-00Z"]
    assert by["catalog-ualr-edu"]["added"] and by["catalog-ualr-edu"]["status"] == "limit_reached"
    assert [r["catalog"] for r in rows][0] == "empty-example-com"  # newest crawl first
    assert crawls.matches(c, "cuesta 27137") and not crawls.matches(c, "ualr")


def test_add_copies_indexes_and_names_the_catalog(roots):
    src, dst = roots
    steps = []
    out = crawls.add_catalog(dst, src, "cuesta-curriqunet-com-catalog-iq-27137", by="Eric Riddoch",
                             progress=lambda **kw: steps.append(kw["step"]), log=lambda *a, **k: None)
    assert out["pages"] == 3 and out["crawl"] == "2026-10-21T10-00-00Z"
    assert steps[0] == "copying" and steps[-1] == "done"
    cat = manifest.catalog_entry(manifest.load(dst)[0], "cuesta-curriqunet-com-catalog-iq-27137", create=False)
    assert cat["name"] == "Cuesta" and cat["added_by"] == "Eric Riddoch"
    assert cat["current_crawl"] == "2026-10-21T10-00-00Z" and cat["crawls"][0]["page_count"] == 3
    assert crawls.added_catalogs(dst) == {"cuesta-curriqunet-com-catalog-iq-27137"}
    # again: nothing left to copy, still fine
    crawls.add_catalog(dst, src, "cuesta-curriqunet-com-catalog-iq-27137", log=lambda *a, **k: None)


def test_add_refuses_a_crawl_without_pages(roots):
    from golden_datasets.errors import UserError

    src, dst = roots
    with pytest.raises(UserError, match="no pages"):
        crawls.add_catalog(dst, src, "empty-example-com")


def test_api_search_add_and_the_new_card(roots):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    src, dst = roots
    c = TestClient(create_app(dst.uri, crawls_root=src.uri))
    items = c.get("/api/crawls").json()["items"]
    assert {i["catalog"] for i in items} >= {"cuesta-curriqunet-com-catalog-iq-27137"}
    assert c.post("/api/crawls/empty-example-com/add", json={}).status_code == 400
    job = c.post("/api/crawls/cuesta-curriqunet-com-catalog-iq-27137/add", json={"by": "Jared Diener"}).json()
    assert job["name"] == "Cuesta"
    for _ in range(100):
        cards = {x["catalog"]: x for x in c.get("/api/catalogs").json()}
        card = cards["cuesta-curriqunet-com-catalog-iq-27137"]
        if card["status"] != "adding":
            break
        time.sleep(0.05)
    assert card["status"] == "not imported" and card["name"] == "Cuesta" and card["pages"] == 3
    assert c.post("/api/crawls/cuesta-curriqunet-com-catalog-iq-27137/add", json={}).status_code == 409
    added = {i["catalog"]: i["added"] for i in c.get("/api/crawls").json()["items"]}
    assert added["cuesta-curriqunet-com-catalog-iq-27137"]
