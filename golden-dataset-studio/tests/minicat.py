"""A six-course catalog shaped like AVC, for fast tests of AI runs (one-rule-runs spec): Credit Value and the Credit
Unit Type that reads it, Description, Subject Webpage (the page's address) and In Catalog (no rule yet). Built with
the real CLI: crawl → `crawls add` → `rule publish` (ruleset v1)."""

from __future__ import annotations

import json
from pathlib import Path

from golden_datasets import crawls
from golden_datasets.cli import main
from golden_datasets.context import Ctx
from golden_datasets.storage import LocalRoot

CAT = "cuesta-curriqunet-com-catalog-iq-27137"
SEED = "https://cuesta.curriqunet.com/catalog/iq/27137/"
COURSES = [  # code, title, credits, description
    ("ACCT 199", "Work Experience Education", "1.0 - 8.0 Units",
     "Advisory: Eligibility for ENGL 101.<br>Students gain work experience in accounting."),
    ("BIOL 110", "General Biology", "4.0 Units",
     "Prerequisite: None.<br>A comprehensive and in-depth introduction for all biology majors."),
    ("GEOG 222", "Physical Geography", "3.0 Units", "Landforms, climate and water."),
    ("KINF 244", "Fitness Walking", "1.0 Units", "Walking for health."),
    ("AERO 199", "Aerospace Work Experience", "1.0 - 4.0 Units", "Advisory: Eligibility for ENGL 101.<br>Work."),
    ("CFE 114", "Child Growth", "3.0 Units", "Growth from birth to adolescence."),
]
RULES = {"catalog": CAT, "settings": {"content_root": "body"}, "rules": [
    {"rule_id": "course-page", "kind": "page", "definition": {"url_regex": "/c/\\d+$", "label": "Course"}},
    {"rule_id": "locator-course-page", "kind": "locator",
     "definition": {"page_rules": ["course-page"], "scope": None, "repeat": None, "repeat_filter": None}},
    {"rule_id": "course-code", "kind": "property", "property_label": "Coded Notation",
     "ctdl_property": "ceterms:codedNotation",
     "definition": {"locator": "locator-course-page", "rule_type": "css+regex", "selector": "h1",
                    "regex": "^([A-Z]+ \\d+)", "group": 1, "transforms": ["collapse_ws"]}},
    {"rule_id": "course-name", "kind": "property", "property_label": "Learning Opportunity Name",
     "ctdl_property": "ceterms:name",
     "definition": {"locator": "locator-course-page", "rule_type": "css", "selector": "title",
                    "transforms": ["collapse_ws"]}},
    {"rule_id": "course-credit-value", "kind": "property", "property_label": "Credit Value",
     "ctdl_property": "ceterms:creditValue",
     "definition": {"locator": "locator-course-page", "rule_type": "css", "selector": "p.meta",
                    "transforms": ["collapse_ws"]}},
    {"rule_id": "course-credit-value-credit-unit-type", "kind": "property", "property_label": "Credit Unit Type",
     "ctdl_property": "ceterms:creditValue>qdata:creditUnitType",
     "definition": {"locator": "locator-course-page", "rule_type": "regex",
                    "input": {"from": "rule", "rule": "course-credit-value"}, "regex": "([A-Za-z]+)\\s*$"}},
    {"rule_id": "course-description", "kind": "property", "property_label": "Description",
     "ctdl_property": "ceterms:description",
     "definition": {"locator": "locator-course-page", "rule_type": "css", "selector": "div.desc",
                    "transforms": ["strip"]}},
    {"rule_id": "course-subject-webpage", "kind": "property", "property_label": "Subject Webpage",
     "ctdl_property": "ceterms:subjectWebpage", "definition": {"locator": "locator-course-page", "rule_type": "source_url"}},
    {"rule_id": "course-in-catalog", "kind": "property", "property_label": "In Catalog",
     "ctdl_property": "ceterms:inCatalog", "definition": {"locator": "locator-course-page", "rule_type": "none"}},
]}


def crawl(base: Path) -> None:
    d = base / CAT / "2026-10-21T10-00-00Z"
    (d / "pages").mkdir(parents=True)
    (d / "crawl.json").write_text(json.dumps({"seed_url": SEED, "status": "complete", "pages_saved": len(COURSES),
                                              "started_at": "2026-10-01T00:00:00Z",
                                              "finished_at": "2026-10-21T12:00:00Z"}))
    for i, (code, title, credits, desc) in enumerate(COURSES):
        stem = f"page-{i}"
        html = (f"<html><head><title>{code} - {title}</title></head><body><h1>{code} - {title}</h1>"
                f"<p class=\"meta\">{credits}</p><div class=\"desc\">{desc}</div></body></html>").encode()
        (d / "pages" / f"{stem}.html").write_bytes(html)
        (d / "pages" / f"{stem}.meta.json").write_text(json.dumps({
            "stem": stem, "requested_url": f"{SEED}c/{i}", "final_url": f"{SEED}c/{i}", "http_status": 200,
            "retrieved_at": "2026-10-01T00:00:00Z", "bytes": len(html), "sha256": "x"}))


def build(tmp_path: Path) -> Path:
    """The catalog at ruleset v1, in `tmp_path/root`."""
    src, dst = LocalRoot(tmp_path / "xtra-cli-output"), tmp_path / "root"
    crawl(src.base)
    dst.mkdir()
    crawls.add_catalog(LocalRoot(dst), src, CAT, log=lambda *a, **k: None)
    draft = tmp_path / "first.json"
    draft.write_text(json.dumps(RULES))
    assert main(["rule", "publish", "--root", str(dst), "--catalog", CAT, str(draft), "--note", "first"]) == 0
    return dst


def ctx(root: Path) -> Ctx:
    return Ctx(LocalRoot(root), CAT)


def cli(root: Path, *argv: str) -> int:
    return main([*argv, "--root", str(root), "-c", CAT])


def draft(root: Path, tmp_path: Path, capsys, name: str, *rules: str, edit=None) -> str:
    """`rule draft` → edit(doc) → a draft file."""
    capsys.readouterr()
    assert cli(root, "rule", "draft", *rules) == 0
    doc = json.loads(capsys.readouterr().out)
    if edit:
        edit({r["rule_id"]: r for r in doc["rules"]})
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


def mark(root: Path, rule: str, course: str, verdict: str | None, author: str = "Jared Diener",
         note: str | None = None, expected: str | None = None, at: str | None = None, role: str = "sme") -> str:
    """Append a verdict (or, with verdict None, a comment) on a course's row, as the Studio would. Returns its id."""
    from datetime import UTC, datetime

    from golden_datasets.log import new_id
    from golden_datasets.review import LOADER

    c = ctx(root)
    c.invalidate()
    snap = LOADER.snapshot(c, c.latest_extraction())
    row = next(r for r in snap.rows(rule) if r["course_key"] == course)
    aid = new_id()
    LOADER.log(c).append({
        "annotation_id": aid, "type": "verdict" if verdict else "comment",
        "at": at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "author": author, "author_role": role,
        "catalog": CAT, "crawl": c.crawl,
        "target": {"kind": "match", "rule_id": rule, "rule_version_seen": snap.rules[rule]["version"],
                   "extraction_seen": snap.ext, "occurrence_key": row["occurrence_key"], "course_key": course,
                   "page_stem": row["page_stem"], "value_index": 0, "value_seen": row["value"]},
        "verdict": verdict, "expected": {"text": expected} if expected is not None else None, "note": note,
        "supersedes": None})
    return aid
