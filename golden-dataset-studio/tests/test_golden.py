"""Golden publication on a copy of the AVC demo root (ruleset v1 → v2): the gate, the existing per-page shape plus
`golden_id` and `location`, lineage complete and domain-only output (spec §5.6, §7.6). Marked `slow`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from golden_datasets import check, golden
from golden_datasets.context import Ctx
from golden_datasets.errors import UserError
from golden_datasets.storage import LocalRoot
from golden_datasets.sync import sync_catalog

DEMO = Path(__file__).resolve().parents[1] / ".data" / "root-demo"


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    if not (DEMO / "golden-dataset-studio" / "manifest.json").exists():
        pytest.skip("demo root not built (.data/root-demo)")
    root = LocalRoot(tmp_path_factory.mktemp("gold") / "root")
    sync_catalog(LocalRoot(DEMO), root, "avc-elumenapp-com-catalog-2026-27-welcome", None, "link", False, False)
    return Ctx(root, "avc")


@pytest.mark.slow
def test_gate_refuses_until_every_rule_is_approved(ctx, tmp_path):
    with pytest.raises(UserError, match="not approved"):
        golden.publish(ctx, str(tmp_path / "out"), "test")


@pytest.mark.slow
def test_publication_shape_and_lineage(ctx, tmp_path):
    out = tmp_path / "out"
    doc = golden.publish(ctx, str(out), "test", allow_unapproved=True)
    assert doc["approval_gate"]["all_rules_approved"] is False
    assert doc["pages"] == 1259 and doc["courses"] == 1075
    stem = next(s for s in doc["page_stems"] if "course-geog222-" in s)
    page = out / doc["to_prefix"] / stem
    records = json.loads((page / f"{stem}.json").read_text())
    assert (page / f"{stem}.html").exists()
    assert [r["golden_id"] for r in records] == ["GEOG222"]
    fields = {f["property"]: f for f in records[0]["fields"]}
    assert set(fields) == {"Coded Notation", "External Identifier", "Learning Opportunity Name", "Description",
                           "Subject Webpage", "Learning Type", "Life Cycle Status Type", "Language"}
    assert fields["Learning Type"]["ctdl_property"] is None and fields["Learning Type"]["location"] is None
    assert fields["Description"]["value"].startswith("This course provides")  # v2: no prerequisite line
    assert fields["Description"]["location"]["css_path"].startswith("html > body")
    assert not any(k in json.dumps(records) for k in ("rule_id", "occurrence_key", "annotation_ids"))
    failed = [r for r in check.run(Ctx(ctx.root, "avc")) if r[3] and r[0] in ("lineage", "golden page")]
    assert not failed, failed


@pytest.mark.slow
def test_golden_api_blocks_publish_until_approved(ctx):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    c = TestClient(create_app(ctx.root.uri))
    d = c.get("/api/catalogs/avc/golden").json()
    assert d["ready"] is False and d["pages"] == 1259 and d["courses"] == 1075
    assert sum(r["status"] == "approved" for r in d["rules"]) == 5 and d["collisions"] == []
    assert d["target"].endswith("/golden-out/avc-elumenapp-com-catalog-2026-27-welcome/2026-10-12T20-59-13Z/")
    r = c.post("/api/catalogs/avc/golden/publish", json={"author": "Test"})
    assert r.status_code == 409 and "not approved" in r.json()["detail"]
