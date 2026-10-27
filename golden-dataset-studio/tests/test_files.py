"""Storage files: the debugging view of a catalog's Studio files (routes_files.py)."""

from __future__ import annotations

import pytest

from golden_datasets.cli import main
from golden_datasets.server.routes_files import about, group


def test_about_and_group():
    c = "avc-x"
    assert "immutable" in about(f"{c}/golden-dataset-studio/rules/course-code/v0001.json")
    assert "append-only" in about(f"{c}/golden-dataset-studio/annotations.jsonl")
    assert group("golden-dataset-studio/manifest.json", c) == "Root"
    assert group(f"{c}/golden-dataset-studio/rulesets/v0002.json", c) == "Rulesets"
    assert group(f"{c}/2026/golden-dataset-studio/extractions/rs-0001/matches.parquet", c) == "Extractions"
    assert group(f"{c}/2026/crawl.json", c) == "Crawl"


@pytest.fixture(scope="module")
def client(tmp_path_factory, avc_v1_root):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    dst = tmp_path_factory.mktemp("files") / "root"
    assert main(["sync", "--from", str(avc_v1_root), "--to", str(dst), "-c", "avc", "--pages", "link"]) == 0
    return TestClient(create_app(str(dst)))


@pytest.mark.slow
def test_list_and_preview(client):
    d = client.get("/api/catalogs/avc/files").json()
    paths = [f["path"] for f in d["files"]]
    assert d["portal"] is None  # a local root has no Azure portal links
    assert "golden-dataset-studio/manifest.json" in paths
    assert not any("/pages/" in p or "/assets/files/" in p for p in paths)
    log = next(p for p in paths if p.endswith("annotations.jsonl"))
    ev = client.get("/api/catalogs/avc/files/content", params={"path": log, "limit": 3}).json()
    assert ev["kind"] == "jsonl" and len(ev["rows"]) == 3 and ev["rows"][0]["line"] == ev["total"]  # newest first
    geog = client.get("/api/catalogs/avc/files/content", params={"path": log, "q": "geog222"}).json()
    assert 0 < geog["matched"] < geog["total"]
    matches = next(p for p in paths if p.endswith("matches.parquet"))
    t = client.get("/api/catalogs/avc/files/content", params={"path": matches, "limit": 5, "q": "GEOG222"}).json()
    assert t["kind"] == "table" and "rule_id" in t["columns"] and 0 < t["matched"] < t["total"] and len(t["rows"]) == 5
    rule = next(p for p in paths if p.endswith("/rules/course-description/v0001.json"))
    j = client.get("/api/catalogs/avc/files/content", params={"path": rule}).json()
    assert j["kind"] == "json" and '"rule_id": "course-description"' in j["text"]
    assert client.get("/api/catalogs/avc/files/content", params={"path": "../secrets"}).status_code == 404
