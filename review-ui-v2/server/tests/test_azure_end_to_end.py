"""The whole workflow with Azure as the only storage: sample, extract (with worker
processes), review, flag, export, restart. Runs against Azurite."""

import json

import pytest
from conftest import (
    SAMPLE_STEMS,
    build_run,
    fixture_url,
    publish_rules,
    seed_template,
    upload_tree,
)
from fastapi.testclient import TestClient

from review_ui import cli
from review_ui.api import create_app
from review_ui.runs import find_runs
from review_ui.store import open_store

URL = fixture_url("course_admj")


@pytest.fixture
def root(azure_container, tmp_path):
    """The fake crawl uploaded to a fresh Azure container; returns the azure:// root."""
    local = tmp_path / "local"
    build_run(local, "cat/cat/2026-01-01T00-00-00Z", "cat", "2026-01-01T00:00:00Z")
    upload_tree(azure_container[1], local)
    # Template and ruleset live in the same container as the crawl, like the crawl itself.
    seed_template(azure_container[1])
    publish_rules(azure_container[1], catalog_folder="cat", ruleset_id="cat")
    return azure_container[1]


def run_cli(root, *args):
    return cli.main([args[0], "--root", root, "--run", "cat", *args[1:]])


def test_the_full_workflow_runs_on_azure(root, capsys):
    store = open_store(root)
    (run,) = find_runs(root)
    assert run.key == "cat/cat/2026-01-01T00-00-00Z" and run.catalog_folder == "cat"

    assert (
        run_cli(root, "sample", "--size", "5") == 0
    )  # ruleset read from the container
    assert store.exists(f"{run.key}/review-ui/sample.json")
    # Worker processes rebuild the Azure store themselves from the root string.
    assert run_cli(root, "extract", "--workers", "2") == 0
    (extraction,) = store.list_dir(f"{run.key}/extractions")
    assert store.exists(f"{run.key}/extractions/{extraction}/report.json")
    assert '"records"' in capsys.readouterr().out

    client = TestClient(create_app(root, run))
    cid = "cat-2026-01-01t00-00-00z"
    state = client.get(f"/api/c/{cid}/state").json()
    assert state["run"]["key"] == run.key and len(state["pages"]) == 5
    review_id = state["review"]["session"]["review_id"]
    stem = state["pages"][0]["stem"]

    page = client.get(f"/api/c/{cid}/pages/{stem}").json()
    field = page["records"][0]["fields"][0]
    base = f"/api/c/{cid}"
    accept = {
        "type": "decision",
        "author": "Seth",
        "kind": "field",
        "key": field["field_id"],
        "status": "accepted",
        "canonical_label": field["canonical_label"],
        "source_url": field["source_url"],
        "value": field["value"],
    }
    assert client.post(f"{base}/events", json=accept).status_code == 200
    flag = {
        "type": "flag",
        "author": "Jared",
        "scope": "page",
        "target": f"page::{stem}",
        "stem": stem,
        "source_url": page["url"],
        "flagged": True,
        "note": "ask the dean",
    }
    assert client.post(f"{base}/events", json=flag).status_code == 200

    session = f"{run.key}/review-ui/{review_id}"
    assert [e["type"] for e in store.read_jsonl(f"{session}/events.jsonl")] == [
        "decision",
        "flag",
    ]
    assert (
        store.read_json(f"{session}/decisions.json")[field["field_id"]]["status"]
        == "accepted"
    )
    assert (
        store.read_json(f"{session}/flags.json")[f"page::{stem}"]["note"]
        == "ask the dean"
    )
    (entry,) = store.read_json("review-ui-index/index.json")
    assert (entry["accepted"], entry["flagged_pages"]) == (1, 1)

    assert client.get(f"{base}/export/golden/{stem}.json").status_code == 200
    assert "ask the dean" in client.get(f"{base}/export/flagged.md").text
    assert client.get(f"{base}/pages/{stem}/content").status_code == 200

    # A restarted server rebuilds the review from the blobs alone.
    again = TestClient(create_app(root, run))
    restored = again.get(f"{base}/state").json()["review"]
    assert restored["session"]["review_id"] == review_id
    assert restored["decisions"][field["field_id"]]["status"] == "accepted"
    assert restored["flags"][f"page::{stem}"]["note"] == "ask the dean"

    assert run_cli(root, "export-feedback") == 0
    assert "azure://http://127.0.0.1:10000" in capsys.readouterr().out
    assert store.exists(f"{session}/feedback.md")


def test_the_landing_page_lists_a_catalog_whose_ruleset_is_stored_in_azure(root):
    client = TestClient(create_app(root, None))
    (card,) = client.get("/api/catalogs").json()["catalogs"]
    assert (card["catalog_folder"], card["pages"], card["ready"]) == ("cat", 5, False)
    assert card["ruleset"]["id"] == "cat" and "extract --run" in card["hint"]


def test_publishing_a_ruleset_to_azure_through_the_cli(root, tmp_path, capsys):

    from conftest import RULES

    draft = tmp_path / "draft.json"
    draft.write_text(
        json.dumps({**json.loads(RULES.read_text()), "catalog_folder": "second"})
    )
    assert cli.main(["rules", "publish", "--root", root, str(draft)]) == 0
    assert "azure://http://127.0.0.1:10000" in capsys.readouterr().out
    assert open_store(root).exists("review-ui-index/rulesets/second/rules.json")
    assert cli.main(["rules", "list", "--root", root]) == 0
    assert "second  v2" in capsys.readouterr().out


def test_the_sample_stems_exist_as_pages(root):
    store = open_store(root)
    names = store.list_dir("cat/cat/2026-01-01T00-00-00Z/pages")
    assert all(f"{stem}.html" in names for stem in SAMPLE_STEMS)


def test_pages_are_cached_on_first_read_and_the_cache_commands_work(root, capsys):
    from review_ui.cache import CachedStore

    assert run_cli(root, "sample", "--size", "5") == 0
    assert (
        run_cli(root, "extract", "--workers", "2") == 0
    )  # worker processes fill the cache
    store = open_store(root)
    assert isinstance(store, CachedStore)
    assert store.cache.stats().files == 10  # 5 pages and their 5 metadata files
    capsys.readouterr()
    assert cli.main(["cache", "status", "--root", root]) == 0
    assert "10 files" in capsys.readouterr().out
    assert cli.main(["cache", "clear", "--root", root, "--run", "cat"]) == 0
    assert store.cache.stats().files == 0
    assert cli.main(["cache", "warm", "--root", root, "--run", "cat"]) == 0
    assert store.cache.stats().files == 10
    # and the app, reading the same crawl, serves a page from that cache
    client = TestClient(create_app(root, find_runs(root)[0]))
    stem = client.get("/api/c/cat-2026-01-01t00-00-00z/state").json()["pages"][0][
        "stem"
    ]
    assert (
        client.get(f"/api/c/cat-2026-01-01t00-00-00z/pages/{stem}/content").status_code
        == 200
    )


def test_no_cache_leaves_the_cache_folder_empty(root):
    from review_ui.cache import cache_root

    assert run_cli(root, "sample", "--size", "5", "--no-cache") == 0
    assert run_cli(root, "extract", "--workers", "2", "--no-cache") == 0
    assert list(cache_root().glob("**/*.gz")) == []


def test_golden_datasets_are_saved_in_a_separate_azure_container(root):
    assert run_cli(root, "sample", "--size", "5") == 0
    assert run_cli(root, "extract", "--workers", "1") == 0
    (run,) = find_runs(root)
    golden_root = root + "/golden-sets"  # a separate root (prefix)
    golden = open_store(golden_root)
    client = TestClient(create_app(root, run, golden_root=golden_root))
    base = "/api/c/cat-2026-01-01t00-00-00z"
    url = fixture_url("course_admj")
    accept = {
        "type": "decision",
        "author": "Jared",
        "kind": "field",
        "status": "accepted",
        "key": f"ADMJ51::Coded Notation::{url}::0",
        "canonical_label": "Coded Notation",
        "source_url": url,
        "record_id": "ADMJ51",
        "value": "ADMJ 51",
    }
    assert client.post(f"{base}/events", json=accept).status_code == 200
    reply = client.post(f"{base}/golden/course_admj")
    assert reply.status_code == 200, reply.text
    assert golden.read_json(
        "cat/2026-01-01T00-00-00Z/course_admj/course_admj.json"
    ) == [
        {
            "fields": [
                {
                    "ctdl_property": "ceterms:codedNotation",
                    "value": "ADMJ 51",
                    "source_url": url,
                }
            ]
        }
    ]
    assert golden.exists("cat/2026-01-01T00-00-00Z/course_admj/course_admj.html")
