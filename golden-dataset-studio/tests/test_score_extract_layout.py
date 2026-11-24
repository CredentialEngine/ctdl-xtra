"""Today's xtra extract output in the Studio: `xtra catalog extract <property>` writes one file per property of each
resource under `extraction_report/<prefix>/<property key>/`, and one `extraction-<property key>-report.json` per
property, and no `records/`. The Studio reads it through xtra's own `extraction_records`, scores it, and reads
each output where xtra wrote it (approved item 21)."""

from __future__ import annotations

import json

import pytest
from common.keys import page_stem
from test_golden_versions import CAT, studio  # noqa: F401  (studio: the fixture)
from test_scores import scored  # noqa: F401  (a published ruleset v1)

from golden_datasets import scores
from golden_datasets.cli import main
from golden_datasets.context import Ctx
from golden_datasets.errors import UserError
from golden_datasets.storage import LocalRoot

CRAWL = "2026-10-12T20-59-13Z"
ONE = "https://avc.example/course/acct199"   # one course on its page
TWO = "https://avc.example/courses/acct"     # two courses on one page, read in page order
HTML = "<html><body><h2 id='a'>ACCT 101 Bookkeeping</h2><h2 id='b'>ACCT 102 Payroll</h2></body></html>"


def _value(prop: str, rid: str, url: str, value, css: str = "-") -> dict:
    return {"type": "ceterms:Course", "resource_id": rid, "ctdl_property": prop, "value": value, "catalog_id": CAT,
            "source_url": url, "retrieved_at": "2026-10-12T22:05:54Z", "notes": f"strategy=test platform=- css={css}"}


def new_output(folder, crawl: str = CRAWL, name_101: str = "Bookkeeping") -> None:
    """An extract output as today's xtra writes it (name and coded notation), and the saved page it orders by."""
    rows = {
        "ceterms:name": [("acct199", ONE, "Work Experience", "-"), ("acct101", TWO, name_101, "#a"),
                         ("acct102", TWO, "Payroll", "#b")],
        "ceterms:codedNotation": [("acct199", ONE, "ACCT 199", "-"), ("acct101", TWO, "ACCT 101", "#a"),
                                  ("acct102", TWO, "ACCT 102", "#b")],
    }
    for prop, values in rows.items():
        key = prop.replace(":", "_")
        d = folder / "extraction_report" / "ceterms" / key
        d.mkdir(parents=True, exist_ok=True)
        for rid, url, value, css in values:
            (d / f"{CAT}_{rid}.json").write_text(json.dumps(_value(prop, f"{CAT}_{rid}", url, value, css)))
        (folder / f"extraction-{key}-report.json").write_text(json.dumps({
            "schema": "xtra-extraction-report-1", "property": prop, "class": ["ceterms:Course"], "catalog_folder": CAT,
            "run_id": crawl, "discovery_run_id": "d-1", "only_golden_sample": False, "limit": None,
            "resources_written": len(values)}))
    (folder / "pages").mkdir(parents=True, exist_ok=True)
    (folder / "pages" / f"{page_stem(TWO)}.html").write_text(HTML)


def _golden() -> dict[str, list[dict]]:
    def f(prop, value, url):
        return {"ctdl_property": prop, "value": value, "source_url": url, "property": prop}

    return {
        page_stem(ONE): [{"fields": [f("ceterms:name", "Work Experience", ONE), f("ceterms:codedNotation", "ACCT 199", ONE)]}],
        page_stem(TWO): [{"fields": [f("ceterms:name", "Bookkeeping", TWO), f("ceterms:codedNotation", "ACCT 101", TWO)]},
                         {"fields": [f("ceterms:name", "Payroll", TWO), f("ceterms:codedNotation", "ACCT 102", TWO)]}],
    }


def test_todays_extract_output_is_read_as_records_and_scored(tmp_path):
    new_output(tmp_path / "out")
    store = scores.RecordsStore(LocalRoot(tmp_path / "out"), "", CAT, CRAWL)
    assert store.reports() == ["extraction-ceterms_codedNotation-report.json", "extraction-ceterms_name-report.json"]
    # one record per resource, keyed by its page; a page's second resource is the page's second record
    two = page_stem(TWO)
    assert sorted(k.rsplit("/", 1)[1] for k in store.records()) == sorted(
        [f"{page_stem(ONE)}.json", f"{two}.json", f"{two}--resource-002.json"])
    assert store.get_json(f"{CAT}/{CRAWL}/records/{two}--resource-002.json")["expected"]["ceterms:name"] == "Payroll"
    assert scores.emitted(store) == {"ceterms:name", "ceterms:codedNotation", "ceterms:subjectWebpage"}  # its source_url
    reports = scores.run_scorer(store, _golden(), CAT, CRAWL, "test")
    assert reports["exact"]["outcomes"]["match"] == 6 and reports["exact"]["outcomes"]["missing"] == 0


def test_a_new_output_is_registered_once_and_read_where_xtra_wrote_it(studio, tmp_path, monkeypatch):  # noqa: F811
    """Approved item 21: xtra-cli owns its outputs; the Studio registers each one and reads it in place."""
    _, ctx, _ = studio
    ctx = Ctx(ctx.root, CAT)
    src = tmp_path / "xtra-cli-output"
    monkeypatch.setenv("GOLDEN_DATASETS_XTRA_SOURCE", str(src))
    new_output(src / CAT / ctx.crawl, ctx.crawl)
    entry, new = scores.see_output(ctx, log=lambda *a: None)
    assert new and entry["records"] == 3 and entry["records_written"] is None and not entry["records_mismatch"]
    assert entry["properties"] == ["ceterms:codedNotation", "ceterms:name"] and entry["run_id"] == ctx.crawl
    assert entry["copy"] is None and not list((ctx.root.local_path(".").parent).glob("**/extract-outputs"))
    kept = scores.output_store(Ctx(ctx.root, CAT), entry)
    assert kept.get_json(f"{CAT}/{ctx.crawl}/records/{page_stem(ONE)}.json")["expected"]["ceterms:codedNotation"] == "ACCT 199"
    # seen again: the same output
    again, new = scores.see_output(Ctx(ctx.root, CAT), log=lambda *a: None)
    assert not new and again["id"] == entry["id"]
    # xtra writes the property again: a new output, and the old one can't be read any more
    new_output(src / CAT / ctx.crawl, ctx.crawl, name_101="Bookkeeping I")
    (src / CAT / ctx.crawl / "extraction-ceterms_name-report.json").write_text(json.dumps({
        "property": "ceterms:name", "run_id": ctx.crawl, "resources_written": 3, "again": True}))
    third, new = scores.see_output(Ctx(ctx.root, CAT), log=lambda *a: None)
    assert new and third["report_etag"] != entry["report_etag"]
    with pytest.raises(UserError, match="newer output"):
        scores.output_store(Ctx(ctx.root, CAT), entry)


def test_the_score_command_reads_a_new_layout_folder_in_place(scored, capsys):  # noqa: F811
    _, ctx, tmp = scored
    new_output(tmp / "run", ctx.crawl)
    assert main(["score", "--class", "course", "--root", ctx.root.uri, "--catalog", CAT, "--output", str(tmp / "run")]) == 0
    capsys.readouterr()
    doc = scores.read(Ctx(ctx.root, CAT), "sc-0001")
    assert doc["status"] == "done" and doc["output"]["records"] == 3
    assert doc["output"]["properties"] == ["ceterms:codedNotation", "ceterms:name"]
    assert "name" in doc["xtra_extracts"] and "codedNotation" in doc["xtra_extracts"]
