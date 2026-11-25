"""A small LearningProgram fixture (LearningProgram plan, Phase 1): two WVU program pages that print their major codes
and one AVC program page that prints none, as two catalogs. Built with the real CLI: crawl → `crawls add` →
`rule publish --class learningprogram` (ruleset v1).

The External Identifier follows issue #368 (approved item 5): WVU's printed code (the first one when a page prints
two: ask 1), AVC's generated `program-<normalized name>` (ask 3)."""

from __future__ import annotations

import json
from pathlib import Path

from golden_datasets import crawls
from golden_datasets.cli import main
from golden_datasets.storage import LocalRoot

CRAWL = "2026-11-20T10-00-00Z"
WVU, AVC = "catalog-wvu-edu", "avc-elumenapp-com-catalog-2026-27-welcome"
#: catalog → [(url, html body)]
PAGES = {
    WVU: [
        ("https://catalogs.wvu.edu/undergraduate/businessandeconomics/accountancy/",
         "<h1 class=\"page-title\">Accountancy, B.S.B.A.</h1><div id=\"textcontainer\">"
         "<p><strong>In-Person Major Code:</strong> 2166</p>"
         "<p class=\"desc\">The accountancy program prepares students for careers in public accounting.</p></div>"),
        ("https://catalogs.wvu.edu/undergraduate/statler/miningengineering/",
         "<h1 class=\"page-title\">Mining Engineering, B.S.Min.E.</h1><div id=\"textcontainer\">"
         "<p><strong>In-Person Major Code:</strong> 5542 <strong>Online Major Code:</strong> 5545</p>"
         "<p class=\"desc\">Mining engineers plan and design safe, productive mines.</p></div>"),
    ],
    AVC: [
        ("https://avc.elumenapp.com/catalog/2026-27/program/accounting-aa-fall-2026",
         "<main><h1>Accounting, A.A.</h1><div class=\"program-description\">The Accounting degree prepares students "
         "for transfer to a four-year accounting program.</div></main>"),
    ],
}
EXPECTED_IDS = {WVU: ["2166", "5542"], AVC: ["program-accounting-a.a."]}


def _rules(catalog: str) -> dict:
    wvu = catalog == WVU
    loc = "locator-learningprogram-page"
    ident = ({"rule_type": "css+regex", "selector": "#textcontainer p", "regex": r"Major Code:\s*(\w+)", "group": 1}
             if wvu else {"rule_type": "css", "selector": "h1", "transforms": ["collapse_ws", "generated_id:program"]})
    return {"catalog": catalog, "settings": {"content_root": "body"}, "rules": [
        {"rule_id": "learningprogram-page", "kind": "page",
         "definition": {"url_regex": "/(undergraduate|graduate)/" if wvu else "/program/", "label": "LearningProgram"}},
        {"rule_id": loc, "kind": "locator",
         "definition": {"page_rules": ["learningprogram-page"], "scope": None, "repeat": None, "repeat_filter": None}},
        {"rule_id": "learningprogram-external-id", "kind": "property", "property_label": "External Identifier",
         "ctdl_property": "ceterms:identifier", "definition": {"locator": loc, **ident}},
        {"rule_id": "learningprogram-name", "kind": "property", "property_label": "Name", "ctdl_property": "ceterms:name",
         "definition": {"locator": loc, "rule_type": "css", "selector": "h1", "transforms": ["collapse_ws"]}},
        {"rule_id": "learningprogram-description", "kind": "property", "property_label": "Description",
         "ctdl_property": "ceterms:description",
         "definition": {"locator": loc, "rule_type": "css",
                        "selector": "p.desc" if wvu else "div.program-description", "transforms": ["collapse_ws"]}},
        {"rule_id": "learningprogram-subject-webpage", "kind": "property", "property_label": "Subject Webpage",
         "ctdl_property": "ceterms:subjectWebpage", "definition": {"locator": loc, "rule_type": "source_url"}},
    ]}


def crawl(base: Path) -> None:
    for catalog, pages in PAGES.items():
        d = base / catalog / CRAWL
        (d / "pages").mkdir(parents=True)
        (d / "crawl.json").write_text(json.dumps({"seed_url": pages[0][0], "status": "complete",
                                                  "pages_saved": len(pages), "started_at": "2026-11-20T00:00:00Z",
                                                  "finished_at": "2026-11-20T12:00:00Z"}))
        for i, (url, body) in enumerate(pages):
            stem = f"program-{i}"
            html = f"<html><head><title>{url}</title></head><body>{body}</body></html>".encode()
            (d / "pages" / f"{stem}.html").write_bytes(html)
            (d / "pages" / f"{stem}.meta.json").write_text(json.dumps({
                "stem": stem, "requested_url": url, "final_url": url, "http_status": 200,
                "retrieved_at": "2026-11-20T00:00:00Z", "bytes": len(html), "sha256": "x"}))


def build(tmp_path: Path) -> Path:
    """Both catalogs at LearningProgram ruleset v1, in `tmp_path/root`."""
    src, dst = LocalRoot(tmp_path / "xtra-cli-output"), tmp_path / "root"
    crawl(src.base)
    dst.mkdir()
    for catalog in PAGES:
        crawls.add_catalog(LocalRoot(dst), src, catalog, log=lambda *a, **k: None)
        draft = tmp_path / f"{catalog}.json"
        draft.write_text(json.dumps(_rules(catalog)))
        assert main(["rule", "publish", "--class", "learningprogram", "--root", str(dst), "--catalog", catalog,
                     str(draft), "--note", "first LearningProgram rules"]) == 0
    return dst
