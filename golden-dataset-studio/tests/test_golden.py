"""Golden publication on a copy of the AVC demo root (ruleset v1 → v2): the gate, the existing per-page shape plus
`golden_record_id` and `location`, lineage complete and domain-only output (spec §5.6, §7.6). Marked `slow`.
Versions and human-reviewed values on a small catalog: test_golden_versions.py."""

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
ALL = ["Coded Notation", "External Identifier", "Learning Opportunity Name", "Description", "Subject Webpage",
       "Learning Type", "Life Cycle Status Type", "Language"]


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    if not (DEMO / "golden-dataset-studio" / "manifest.json").exists():
        pytest.skip("demo root not built (.data/root-demo)")
    root = LocalRoot(tmp_path_factory.mktemp("gold") / "root")
    sync_catalog(LocalRoot(DEMO), root, "avc-elumenapp-com-catalog-2026-27-welcome", None, "link", False, False)
    return Ctx(root, "avc")


@pytest.mark.slow
def test_a_property_is_published_once_its_rule_is_approved(ctx, tmp_path):
    with pytest.raises(UserError, match="not approved yet: Description"):
        golden.publish(ctx, str(tmp_path / "out"), "test", properties=["Description"])
    doc = golden.publish(ctx, str(tmp_path / "out"), "test")  # default: every property whose rule is approved
    assert doc["properties"] == ["Subject Webpage", "Learning Type", "Life Cycle Status Type", "Language"]
    assert {r["status"] for r in doc["property_gate"]} == {"approved"}
    assert {r["rule_id"] for r in doc["identity_rules"]} >= {"course-page", "locator-course-page"}


@pytest.mark.slow
def test_properties_published_one_at_a_time_add_up(ctx, tmp_path):
    out = tmp_path / "steps"
    first = golden.publish(ctx, str(out), "test", allow_unapproved=True, properties=["Description"])
    stem = next(s for s in first["page_stems"] if "course-abdy112-" in s)  # nobody reviewed ABDY112
    read = lambda: {f["property"] for f in json.loads(  # noqa: E731
        (out / first["to_prefix"] / stem / f"{stem}.json").read_text())[0]["fields"]}
    assert "Description" in read() and "Learning Opportunity Name" not in read()  # (+ columns approved earlier)
    golden.publish(ctx, str(out), "test", allow_unapproved=True, properties=["Learning Opportunity Name"])
    both = read()
    assert {"Learning Opportunity Name", "Description"} <= both
    golden.publish(ctx, str(out), "test", allow_unapproved=True, properties=["Description"])  # columns only grow
    assert read() == both
    owner = golden.published_properties(Ctx(ctx.root, "avc"), str(out))
    assert set(owner) >= {"Description", "Learning Opportunity Name"}
    results = check.run(Ctx(ctx.root, "avc"))
    failed = [r for r in results if r[3] and r[0] in ("lineage", "golden page")]
    assert not failed, failed


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
    assert [r["golden_record_id"] for r in records] == ["GEOG222"]
    fields = {f["property"]: f for f in records[0]["fields"]}
    assert set(fields) == {"Coded Notation", "External Identifier", "Learning Opportunity Name", "Description",
                           "Subject Webpage", "Life Cycle Status Type", "Language"}  # Learning Type has no CTDL term
    assert fields["Description"]["value"].startswith("This course provides")  # v2: no prerequisite line
    assert fields["Description"]["location"]["css_path"].startswith("html > body")
    # who approved each value: Jared selected GEOG222's description (v2 now gives it), the constant Language is the rule's
    assert (fields["Description"]["approval"], fields["Description"]["approved_by"]) == ("human", "Jared")
    assert fields["Language"]["approval"] == "human"  # Jared reviewed every field of GEOG222 in v2
    assert records[0]["approval"] == "human" and list(records[0])[:2] == ["golden_record_id", "approval"]
    other = next(s for s in doc["page_stems"] if "course-abdy112-" in s)  # nobody reviewed ABDY112
    rec = json.loads((out / doc["to_prefix"] / other / f"{other}.json").read_text())[0]
    lang = next(f for f in rec["fields"] if f["property"] == "Language")
    assert (lang["approval"], lang["approved_by"]) == ("rule", "golden-datasets import-v2") and rec["approval"] == "rule"
    assert doc["approvals"]["by_property"]["Description"]["human"] >= 5 and doc["approvals"]["rule"] > doc["approvals"]["human"]
    import pyarrow.parquet as pq

    lin = pq.read_table(ctx.root.local_path(f"{doc['to_prefix'].split('/')[0]}/{doc['to_prefix'].split('/')[1]}"
                                            f"/golden-dataset-studio/golden/{doc['publication']}/lineage.parquet")).to_pylist()
    geog = next(r for r in lin if r["golden_record_id"] == "GEOG222" and r["property"] == "Description")
    lt = next(r for r in lin if r["golden_record_id"] == "GEOG222" and r["property"] == "Learning Type")
    assert lt["ctdl_property"] is None  # kept in the lineage, not in the files
    assert (geog["approval"], geog["approved_by"]) == ("human", "Jared") and geog["approved_at"]
    assert not any(k in json.dumps(records) for k in ("rule_id", "occurrence_key", "annotation_ids"))
    failed = [r for r in check.run(Ctx(ctx.root, "avc")) if r[3] and r[0] in ("lineage", "golden page")]
    assert not failed, failed
