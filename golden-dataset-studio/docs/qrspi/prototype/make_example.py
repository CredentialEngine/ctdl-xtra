"""Build the Golden Dataset Studio example storage root for AVC (throwaway prototype).

    uv run --python <scratch venv> python make_example.py [--no-fetch]

Reads (never writes) the local mirror ~/review-ui-v3-data/xtra-cli-output and imports the
v2 engine read-only. Writes only under studio.ROOT (scratchpad). Steps, in the order of
spec §3.2 plus the course-description v2 iteration:

  init        pages.parquet (+ symlinked pages/ and crawl.json)
  assets      assets/assets.parquet + page_assets.parquet + files/<sha256>   (CSS + fonts)
  import-v2   rules/<id>/v0001.json, rulesets/v0001.json
  extract     extractions/rs-0001/*
  import-v2   annotations.jsonl (Jared's 2026-10-19 session)
  publish     rules/course-description/v0002.json, rulesets/v0002.json, extractions/rs-0002/*
  golden      golden/<pub>/<page_stem>/<page_stem>.json (+ .html) + lineage.parquet + publication.json
  manifest    golden-dataset-studio/manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import lxml.html
import pyarrow as pa
import pyarrow.parquet as pq
from bs4 import BeautifulSoup, Tag
from bs4.element import PreformattedString

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "server"))  # v2 code, imported read-only

from review_ui import engine  # noqa: E402
from review_ui.runs import ROOT_ID  # noqa: E402

import studio  # noqa: E402
from studio import CATALOG, CRAWL, MIRROR, ROOT, STUDIO  # noqa: E402

V2_RUN = MIRROR / CATALOG / CRAWL
V2_EXTRACTION = "2026-10-19T17-27-31Z"
V2_SESSION = "2026-10-19T17-27-55Z"
TIMINGS: dict[str, dict] = {}
NOW = "2026-10-26T12:00:00Z"  # fixed so reruns produce identical files

# ---------------------------------------------------------------------------------------
# Rules: v2 ids -> v3 ids, and the prose (what / how) for v1. `why` is empty for v1.
# ---------------------------------------------------------------------------------------
PAGE_RULES = {
    "label-course-page": (
        "course-page",
        "Pages at /catalog/2026-27/course/<code> that open with the orange course header: the code ('GEOG 222:'), "
        "the title and the units.",
        "The URL path is /catalog/<year>/course/<code> and the main content has a course header "
        "(an h3 inside header.header, which holds the course code).",
    ),
    "label-program-page": (
        "program-page",
        "Pages at /catalog/2026-27/program/<name> for one degree or certificate, with a collapsible 'Program "
        "Requirements' section.",
        "The URL path is /catalog/<year>/program/<slug> and the main content contains the "
        "requirements builder (#accordion-program-builder-rules).",
    ),
    "label-course-on-program-page": (
        "program-page-with-courses",
        "Program pages whose 'Program Requirements' section lists at least one course line, such as "
        "'MATH150 - Calculus and Analytic Geometry   5'.",
        "Same URL test as program-page, and the requirements builder has at least one requirement "
        "line (.new-rule).",
    ),
}
LOCATORS = {
    "locator-course-page": dict(
        page_rules=["course-page"],
        definition={"scope": None, "repeat": None, "repeat_filter": None},
        what="On a course page, everything below the site's top bar (header, intro paragraphs, Units and Hours) "
        "is one course.",
        how="One occurrence per course page: the content root (#mainContent) itself. No repetition.",
    ),
    "locator-program-requirement": dict(
        page_rules=["program-page-with-courses"],
        definition=None,  # filled from v2's `repeat` (identical in every stub rule, research B10)
        what="On a program page, each line in 'Program Requirements' that starts with a course code and ' - ' "
        "('CS150 - Discrete Structures   4'). Heading lines like 'Complete all of the following' are skipped.",
        how="Each .new-rule inside #accordion-program-builder-rules is a candidate. Keep it only when its "
        ".rule-name text starts with a course code followed by ' - ' (for example 'AJ101 - Introduction to "
        "Administration of Justice'); lines such as 'Complete 6 units from…' are skipped.",
    ),
}
FIELD_RULES = {  # v2 rule id -> (locator, what, how). Only the 8 in-scope properties (spec §4.4).
    "course-code": ("locator-course-page",
        "The small code line above the course title in the orange header, e.g. 'GEOG 222:', without the colon.",
        "Text of the h3 in the course header ('GEOG 222:'), trimmed, with the trailing colon removed."),
    "course-external-id": ("locator-course-page",
        "The same code line above the course title, written without spaces: 'GEOG 222:' gives 'GEOG222'.",
        "Same element as Coded Notation (header.header h3); trailing colon removed, then every space removed."),
    "course-name": ("locator-course-page",
        "The large title in the orange course header, e.g. 'Cartography for Geographic Information Science (GIS)'.",
        "Text of the h2 in the course header, trimmed."),
    "course-description": ("locator-course-page",
        "The intro paragraph(s) under the orange course header on a course page, exactly as shown, including any "
        "leading 'Prerequisite:' or 'Advisory:' line.",
        "The whole text of the intro block (.introtext), trimmed and otherwise verbatim."),
    "course-subject-webpage": ("locator-course-page",
        "Nothing on the page itself: the address of the course page, e.g. .../catalog/2026-27/course/geog222.",
        "The URL of the course page itself; nothing is read from the page."),
    "course-learning-type": ("locator-course-page",
        "Nothing on the page itself: every course page gives the fixed value 'Course'.",
        "Constant 'Course'."),
    "course-lifecycle": ("locator-course-page",
        "Nothing on the page itself: every course in this year's catalog gives the fixed value 'Active'.",
        "Constant 'Active'."),
    "course-language": ("locator-course-page",
        "Nothing on the page itself: the catalog never states a language, so every course gives 'English'.",
        "Constant 'English'."),
    "stub-code": ("locator-program-requirement",
        "On a program page's requirement line, the code before ' - ': 'MATH150' in 'MATH150 - Calculus and "
        "Analytic Geometry'.",
        "In the requirement line's .rule-name, the code before ' - ' (letters, an optional letter, digits, "
        "optional letters), trimmed."),
    "stub-external-id": ("locator-program-requirement",
        "The same code at the start of a program requirement line, written without spaces.",
        "Same text as the stub's Coded Notation, with every space removed."),
    "stub-name": ("locator-program-requirement",
        "On a program page's requirement line, the title after ' - ': 'Calculus and Analytic Geometry'.",
        "In the requirement line's .rule-name, the text after ' - ', trimmed."),
    "stub-learning-type": ("locator-program-requirement",
        "Nothing on the page itself: every course line on a program page gives the fixed value 'Course'.",
        "Constant 'Course'."),
}
LOCATOR_KEYS = ("scope", "repeat", "repeat_filter")
CODE_RULE = {"locator-course-page": "course-code", "locator-program-requirement": "stub-code"}

DESCRIPTION_V2 = {
    "definition_patch": {
        "regex": r"\A\s*(?:(?i:pre-?requisites?|co-?requisites?)\s*:[^\n]*?(?:\.[ \t]+(?=[A-Z(])|\n|\Z)\s*)*"
                 r"(\S[\s\S]*?)\s*\Z",
        "group": 1,
    },
    "what": "The intro paragraph(s) under each course's title on a course page, minus any leading "
    "'Prerequisite:' or 'Corequisite:' statement.",
    "how": "Text of the intro block (.introtext). Skip every leading 'Prerequisite:' or 'Corequisite:' "
    "statement (any case, also 'Pre-requisite:' / 'Co-requisite:'). A statement ends at the end of its "
    "line, or at the first '. ' followed by a capital letter when the description continues on the same "
    "line. Keep the rest verbatim, trimmed. If nothing is left, the course has no description (status "
    "empty). 'Advisory:' and 'Limitation on Enrollment:' lines are kept.",
    "why": "Jared marked 5 of the 14 descriptions he reviewed wrong (GEOG222, PHYS102, DFST202, AUTO230, "
    "ENGR955) because the 'Prerequisite: …' line was included. His note: 'Prerequisite should be a "
    "separate property.' Requisites are out of scope for this golden set (spec §1.2), so v2 drops them "
    "from Description instead of moving them. A first draft also dropped 'Advisory:' and 'Limitation on "
    "Enrollment:' lines; `golden-datasets rule try` showed that changed 4 descriptions Jared had marked correct "
    "(ACCT199, AERO199, CFE114, NS922L), so those lines stay until he decides. Known gap: 138 "
    "descriptions still contain a requisite that comes after a kept Advisory/Limitation line "
    "(signal contains-label-text).",
    "examples": [
        {"input": "Prerequisite: Completion of DFST 201.\n\nAdvanced study of ASL grammar.",
         "output": "Advanced study of ASL grammar."},
        {"input": "Intended for students interested in the collision repair industry.",
         "output": "Intended for students interested in the collision repair industry."},
    ],
}

CODE_PATTERN = r"\b[A-Z]{2,5} ?\d{3}[A-Z]?\b"
LABEL_TEXT = r"^\s*(Prerequisites?|Corequisites?|Advisory|Recommended Preparation|Units?|Description|Course)\s*:|\b(Prerequisites?|Corequisites?)\s*:"


# ---------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------
def step(name):
    def deco(fn):
        def run(*a, **kw):
            t = time.perf_counter()
            print(f"[{name}] …", flush=True)
            out = fn(*a, **kw)
            TIMINGS[name] = {"seconds": round(time.perf_counter() - t, 2), **(out or {})}
            print(f"[{name}] {TIMINGS[name]}", flush=True)
            return out
        return run
    return deco


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj) -> str:
    return "sha256:" + hashlib.sha256(canon(obj).encode()).hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_parquet(path: Path, rows: list[dict], schema: pa.Schema) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="zstd")
    return len(rows)


def iso(v2ts: str) -> str:
    """'2026-10-21T20-19-46Z' -> '2026-10-21T20:19:46Z'."""
    d, t = v2ts.split("T")
    return f"{d}T{t[:-1].replace('-', ':')}Z"


def doc_css_path(el) -> str:
    """css_path of an lxml element from the document root (html > body:nth-of-type(1) > …)."""
    parts = []
    while el is not None and isinstance(el.tag, str):
        parent = el.getparent()
        if parent is None:
            parts.append(el.tag)
            break
        same = [s for s in parent if s.tag == el.tag]
        parts.append(f"{el.tag}:nth-of-type({same.index(el) + 1})")
        el = parent
    return " > ".join(reversed(parts))


def map_path(v2path: str, cr_path: str) -> str:
    """v2 anchors css paths at the #xtra-root wrapper; its single child is the content root."""
    anchor = f"#{ROOT_ID}"
    if v2path == anchor:
        return cr_path
    rest = v2path[len(anchor) + 3 :]  # drop '#xtra-root > '
    first, _, tail = rest.partition(" > ")
    assert first.endswith(":nth-of-type(1)"), v2path
    return cr_path + (" > " + tail if tail else "")


def course_key(code: str | None) -> str | None:
    return re.sub(r"\s+", "", code).upper() if code else None


# ---------------------------------------------------------------------------------------
# Step: init (pages.parquet)
# ---------------------------------------------------------------------------------------
PAGES_SCHEMA = pa.schema([
    ("crawl", pa.string()), ("page_stem", pa.string()), ("url", pa.string()),
    ("requested_url", pa.string()), ("http_status", pa.int32()), ("retrieved_at", pa.string()),
    ("bytes", pa.int64()), ("sha256", pa.string()), ("html_path", pa.string()), ("title", pa.string()),
])
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def _page_row(meta_path: str) -> dict:
    meta = json.loads(Path(meta_path).read_text())
    stem = meta["stem"]
    html = (V2_RUN / "pages" / f"{stem}.html").read_text(errors="replace")
    m = _TITLE.search(html[:200_000])
    title = lxml.html.fromstring(m.group(1)).text_content().strip() if m and m.group(1).strip() else None
    return {
        "crawl": CRAWL, "page_stem": stem, "url": meta.get("final_url") or meta["requested_url"],
        "requested_url": meta["requested_url"], "http_status": meta.get("http_status"),
        "retrieved_at": meta.get("retrieved_at"), "bytes": meta.get("bytes"), "sha256": meta.get("sha256"),
        "html_path": f"{CATALOG}/{CRAWL}/pages/{stem}.html", "title": title,
    }


@step("init")
def step_init(pool) -> dict:
    base = ROOT / CATALOG / CRAWL
    base.mkdir(parents=True, exist_ok=True)
    for name in ("pages", "crawl.json"):  # the crawl stays where xtra-cli put it: link, don't copy
        link = base / name
        if not link.exists():
            link.symlink_to(V2_RUN / name)
    metas = sorted(str(p) for p in (V2_RUN / "pages").glob("*.meta.json"))
    rows = list(pool.map(_page_row, metas, chunksize=16))
    rows.sort(key=lambda r: r["page_stem"])
    n = write_parquet(studio.crawl_dir() / "pages.parquet", rows, PAGES_SCHEMA)
    return {"pages": n}


# ---------------------------------------------------------------------------------------
# Step: assets fetch (stylesheets + what they reference). Never runs scripts.
# ---------------------------------------------------------------------------------------
ASSET_SCHEMA = pa.schema([
    ("crawl", pa.string()), ("url", pa.string()), ("final_url", pa.string()), ("status", pa.int32()),
    ("content_type", pa.string()), ("sha256", pa.string()), ("bytes", pa.int64()),
    ("referenced_by", pa.string()), ("fetched_at", pa.string()),
])
PAGE_ASSET_SCHEMA = pa.schema([
    ("crawl", pa.string()), ("page_stem", pa.string()), ("url", pa.string()), ("kind", pa.string()),
])
_CSS_URL = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)|@import\s+['"]([^'"]+)['"]""")


def _page_assets(args) -> list[dict]:
    from urllib.parse import urljoin
    stem, url = args
    html = (V2_RUN / "pages" / f"{stem}.html").read_text(errors="replace")
    doc = lxml.html.fromstring(html)
    base = urljoin(url, (doc.xpath("//base/@href") or [url])[0])
    out = []
    for href in doc.xpath('//link[contains(concat(" ", @rel, " "), " stylesheet ")]/@href'):
        out.append({"crawl": CRAWL, "page_stem": stem, "url": urljoin(base, href), "kind": "stylesheet"})
    for href in doc.xpath('//link[contains(@rel, "icon")]/@href'):
        out.append({"crawl": CRAWL, "page_stem": stem, "url": urljoin(base, href), "kind": "icon"})
    for style in doc.xpath("//style"):
        for a, b in _CSS_URL.findall(style.text or ""):
            u = a or b
            if not u.startswith("data:"):
                out.append({"crawl": CRAWL, "page_stem": stem, "url": urljoin(base, u), "kind": "style-url"})
    seen, uniq = set(), []
    for r in out:
        if r["url"] not in seen:
            seen.add(r["url"])
            uniq.append(r)
    return uniq


@step("assets")
def step_assets(pool, fetch: bool) -> dict:
    import httpx
    from urllib.parse import urljoin

    pages = pq.read_table(studio.crawl_dir() / "pages.parquet").to_pylist()
    page_assets = [r for rows in pool.map(_page_assets, [(p["page_stem"], p["url"]) for p in pages], chunksize=16) for r in rows]
    n_pa = write_parquet(studio.crawl_dir() / "assets" / "page_assets.parquet", page_assets, PAGE_ASSET_SCHEMA)
    todo = list(dict.fromkeys(r["url"] for r in page_assets))
    referenced = {u: "page" for u in todo}
    assets, files = [], studio.crawl_dir() / "assets" / "files"
    files.mkdir(parents=True, exist_ok=True)
    if fetch:
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
        with httpx.Client(follow_redirects=True, timeout=20, headers={"User-Agent": ua}) as client:
            i = 0
            while i < len(todo) and i < 300:
                url = todo[i]
                i += 1
                try:
                    resp = client.get(url, headers={"Referer": "https://avc.elumenapp.com/catalog/2026-27/welcome"})
                    body, status, ctype = resp.content, resp.status_code, resp.headers.get("content-type", "")
                    final = str(resp.url)
                except httpx.HTTPError:
                    body, status, ctype, final = b"", 0, "", url
                digest = hashlib.sha256(body).hexdigest() if body else None
                if digest:
                    (files / digest).write_bytes(body)
                assets.append({"crawl": CRAWL, "url": url, "final_url": final, "status": status,
                               "content_type": ctype.split(";")[0], "sha256": digest, "bytes": len(body),
                               "referenced_by": referenced[url], "fetched_at": NOW})
                if "css" in ctype and body:
                    for a, b in _CSS_URL.findall(body.decode("utf-8", "replace")):
                        child = urljoin(final, a or b)
                        if child.startswith("http") and child not in referenced:
                            # keep only woff2 among font formats, as research §6.3 suggests
                            if re.search(r"\.(woff|ttf|eot|otf)(\?|$)", child):
                                continue
                            referenced[child] = url
                            todo.append(child)
    n_a = write_parquet(studio.crawl_dir() / "assets" / "assets.parquet", assets, ASSET_SCHEMA)
    total = sum(a["bytes"] for a in assets)
    return {"page_assets": n_pa, "assets": n_a, "asset_bytes": total}


# ---------------------------------------------------------------------------------------
# Step: import-v2 rules -> rule versions v1 + ruleset v1
# ---------------------------------------------------------------------------------------
def v2_ruleset() -> dict:
    return json.loads((V2_RUN / "extractions" / V2_EXTRACTION / "rules.json").read_text())


def rule_hash(rule_id: str, rules: dict[str, dict]) -> str:
    """Hash of a rule's definition plus, transitively, the definitions it depends on (spec §4.3)."""
    seen, stack, defs = set(), [rule_id], {}
    while stack:
        rid = stack.pop()
        if rid in seen:
            continue
        seen.add(rid)
        defs[rid] = {"kind": rules[rid]["kind"], "definition": rules[rid]["definition"]}
        stack.extend(rules[rid]["depends_on"])
    return sha(defs)


def build_v1_rules() -> tuple[dict[str, dict], dict]:
    v2 = v2_ruleset()
    rules: dict[str, dict] = {}
    common = lambda rid, kind: {  # noqa: E731
        "catalog": CATALOG, "rule_id": rid, "version": 1, "kind": kind, "parent_version": None,
        "published_by": "golden-datasets import-v2", "published_at": NOW,
    }
    for lr in v2["label_rules"]:
        rid, what, how = PAGE_RULES[lr["rule_id"]]
        definition = {k: lr[k] for k in ("url_regex", "requires_selector", "forbids_selector") if k in lr}
        definition["label"] = lr["label"]
        rules[rid] = {**common(rid, "page"), "ctdl_property": None, "property_label": None,
                      "definition": definition, "what": what, "how": how, "why": "",
                      "examples": [], "depends_on": [],
                      "imported_from": {"v2_rule_id": lr["rule_id"], "v2_description": lr.get("description")}}
    # Record locators: pulled out of the field rules' `repeat` (identical copies, research B10).
    stub_props = next(r for r in v2["field_rules"] if r["rule_id"] == "stub-code")["properties"]
    for rid, spec in LOCATORS.items():
        definition = spec["definition"] or {k: stub_props.get(k) for k in LOCATOR_KEYS}
        for fr in v2["field_rules"]:  # check the claim instead of trusting it
            if FIELD_RULES.get(fr["rule_id"], (None,))[0] == rid:
                got = {k: fr["properties"].get(k) for k in LOCATOR_KEYS}
                assert got == definition, (fr["rule_id"], got, definition)
        definition = {"page_rules": spec["page_rules"], **definition}
        rules[rid] = {**common(rid, "locator"), "ctdl_property": None, "property_label": None,
                      "definition": definition, "what": spec["what"], "how": spec["how"], "why": "",
                      "examples": [], "depends_on": list(spec["page_rules"]),
                      "imported_from": {"v2_field_rules": sorted(
                          f for f, v in FIELD_RULES.items() if v[0] == rid), "v2_key": "properties.repeat"}}
    for fr in v2["field_rules"]:
        if fr["rule_id"] not in FIELD_RULES:
            continue  # out of scope (credit value, credit unit type, …)
        locator, what, how = FIELD_RULES[fr["rule_id"]]
        props = {k: v for k, v in fr["properties"].items() if k not in LOCATOR_KEYS}
        definition = {"locator": locator, "rule_type": fr["rule_type"], **props}
        examples = ([{"input": fr["example_input"], "output": fr["example_output"]}]
                    if "example_input" in fr else [])
        rules[fr["rule_id"]] = {
            **common(fr["rule_id"], "field"), "ctdl_property": fr["ctdl_property"],
            "property_label": fr["canonical_label"], "definition": definition, "what": what, "how": how,
            "why": "", "examples": examples, "depends_on": [locator],
            "imported_from": {"v2_rule_id": fr["rule_id"], "v2_description": fr.get("description")}}
    for rid, rule in rules.items():
        rule["content_hash"] = rule_hash(rid, rules)
    settings = {
        "content_root": v2["content_root"], "page_title": v2["page_title"],
        # v2's pane_css was written for the bare fragment (it hides every svg and restyles .row). Reviewed
        # against the full page (research §6.1): only reveal the collapsed accordions, scoped to content_root.
        "pane_css": ".accordionheader{height:auto!important;overflow:visible!important}"
                    ".accordionheader-x-nested{display:block!important;opacity:1!important;transform:none!important;"
                    "max-height:none!important;pointer-events:auto!important}",
        "pane_css_v2": v2["pane_css"],
        "course_key_rule": CODE_RULE,
        "signals": {"course_code_pattern": CODE_PATTERN, "label_text_pattern": LABEL_TEXT,
                    "shape_outlier_max_share": 0.02, "length_outlier_percentiles": [1, 99],
                    "missed_page_min_codes": 5},
    }
    return rules, settings


ORDER = {"page": 0, "locator": 1, "field": 2}


def ruleset_doc(version: int, rules: dict[str, dict], settings: dict, parent, changed, note, by, extra=None) -> dict:
    listed = sorted(rules.values(), key=lambda r: (ORDER[r["kind"]], r["rule_id"]))
    return {"catalog": CATALOG, "version": version, "parent_version": parent, "published_by": by,
            "published_at": NOW, "note": note, "settings": settings,
            "rules": [{"rule_id": r["rule_id"], "kind": r["kind"], "version": r["version"],
                       "content_hash": r["content_hash"]} for r in listed],
            "changed_rules": changed, **(extra or {})}


def write_rule(rule: dict) -> Path:
    path = studio.catalog_dir() / "rules" / rule["rule_id"] / f"v{rule['version']:04d}.json"
    write_json(path, rule)
    return path


@step("import-v2 rules")
def step_rules() -> dict:
    rules, settings = build_v1_rules()
    for rule in rules.values():
        write_rule(rule)
    rs = ruleset_doc(1, rules, settings, None, sorted(rules), "Imported from review-ui-v2 rules.json "
                     f"(copy in extraction {V2_EXTRACTION}).", "golden-datasets import-v2",
                     {"imported_from": {"v2_ruleset_id": CATALOG, "v2_version": 1,
                                        "v2_rules_json": f"{CATALOG}/{CRAWL}/extractions/{V2_EXTRACTION}/rules.json"}})
    write_json(studio.catalog_dir() / "rulesets" / "v0001.json", rs)
    return {"rules": len(rules), "by_kind": dict(Counter(r["kind"] for r in rules.values()))}


# ---------------------------------------------------------------------------------------
# Step: extract. The v2 engine's own primitives (label test, repeat filter, field rule,
# css_path) run on v2's #xtra-root fragment; paths are then re-anchored at the document root.
# ---------------------------------------------------------------------------------------
LABELS_SCHEMA = pa.schema([
    ("page_stem", pa.string()), ("rule_id", pa.string()), ("rule_version", pa.int32()),
    ("matched", pa.bool_()), ("reason", pa.string()),
])
OCC_SCHEMA = pa.schema([
    ("occurrence_key", pa.string()), ("page_stem", pa.string()), ("page_rule_id", pa.string()),
    ("locator_rule_id", pa.string()), ("locator_rule_version", pa.int32()), ("css_path", pa.string()),
    ("locator_index", pa.int32()), ("course_key", pa.string()),
])
MATCH_SCHEMA = pa.schema([
    ("rule_id", pa.string()), ("rule_version", pa.int32()), ("occurrence_key", pa.string()),
    ("value_index", pa.int32()), ("page_stem", pa.string()), ("course_key", pa.string()),
    ("status", pa.string()), ("value", pa.string()), ("raw_text", pa.string()), ("css_path", pa.string()),
    ("char_start", pa.int32()), ("char_end", pa.int32()),
])
SIGNAL_SCHEMA = pa.schema([
    ("target_kind", pa.string()), ("rule_id", pa.string()), ("occurrence_key", pa.string()),
    ("value_index", pa.int32()), ("page_stem", pa.string()), ("signal", pa.string()),
    ("severity", pa.string()), ("detail", pa.string()),
    ("css_path", pa.string()), ("char_start", pa.int32()), ("char_end", pa.int32()),
])

_W: dict = {}


def _init_worker(rules: dict, settings: dict, only: list[str] | None):
    _W.update(rules=rules, settings=settings, only=only)


def v2_label_rule(rule: dict) -> dict:
    return {"rule_id": rule["rule_id"], "label": rule["definition"]["label"],
            **{k: v for k, v in rule["definition"].items() if k != "label"}}


def v2_field_rule(rule: dict, locator: dict) -> dict:
    d = rule["definition"]
    props = {k: v for k, v in d.items() if k not in ("locator", "rule_type")}
    for k in LOCATOR_KEYS:
        if locator["definition"].get(k):
            props[k] = locator["definition"][k]
    return {"rule_id": rule["rule_id"], "rule_type": d["rule_type"], "canonical_label": rule["property_label"],
            "ctdl_property": rule["ctdl_property"], "applies_to": locator["definition"]["page_rules"],
            "properties": props}


def _label_reason(rule: dict, url: str, soup) -> str:
    d = rule["definition"]
    if "url_regex" in d and not re.search(d["url_regex"], url):
        return "url_mismatch"
    if "requires_selector" in d and (soup is None or soup.select_one(d["requires_selector"]) is None):
        return "missing_required_element"
    if "forbids_selector" in d and soup is not None and soup.select_one(d["forbids_selector"]) is not None:
        return "forbidden_element_present"
    return "matched"


def _extract_page(args) -> dict:
    stem, url = args
    rules, settings, only = _W["rules"], _W["settings"], _W["only"]
    html = (V2_RUN / "pages" / f"{stem}.html").read_text(errors="replace")
    doc = lxml.html.fromstring(html)
    roots = doc.cssselect(settings["content_root"])
    if not roots:
        main_html, cr_path, text = None, None, ""
    else:
        main_html = lxml.html.tostring(roots[0], encoding="unicode", with_tail=False)
        cr_path, text = doc_css_path(roots[0]), roots[0].text_content()
    soup = BeautifulSoup(f'<div id="{ROOT_ID}">{main_html}</div>', "lxml") if main_html else None

    labels, occs, matches, uncovered = [], [], [], []
    page_rules = [r for r in rules.values() if r["kind"] == "page"]
    matched = set()
    for pr in page_rules:
        reason = _label_reason(pr, url, soup)
        assert (reason == "matched") == engine._label_matches(v2_label_rule(pr), url, soup)
        if reason == "matched":
            matched.add(pr["rule_id"])
        labels.append({"page_stem": stem, "rule_id": pr["rule_id"], "rule_version": pr["version"],
                       "matched": reason == "matched", "reason": reason})
    for loc in (r for r in rules.values() if r["kind"] == "locator"):
        page_rule = next((p for p in loc["definition"]["page_rules"] if p in matched), None)
        if page_rule is None or soup is None:
            continue
        ld = loc["definition"]
        scope_el = soup.select_one(ld.get("scope") or f"#{ROOT_ID}")
        if scope_el is None:
            continue
        elements = scope_el.select(ld["repeat"]) if ld.get("repeat") else [scope_el]
        if ld.get("repeat_filter"):
            elements = [e for e in elements if engine._passes_filter(ld["repeat_filter"], e)]
        fields = [r for r in rules.values() if r["kind"] == "field" and r["definition"]["locator"] == loc["rule_id"]]
        if only is not None:
            fields = [f for f in fields if f["rule_id"] in only]
        for index, element in enumerate(elements):
            occ_path = map_path(engine.css_path(element), cr_path)
            key = f"{stem}@{occ_path}"
            rows = []
            for fr in fields:
                v2r = v2_field_rule(fr, loc)
                res = engine._run_field_rule(v2r, element, url)
                if res["presence"] == "present":
                    status = "found"
                else:
                    sel = fr["definition"].get("selector")
                    status = "no_match" if sel and element.select_one(sel) is None else "empty"
                loc_ = res.get("location") or {}
                rows.append({"rule_id": fr["rule_id"], "rule_version": fr["version"], "occurrence_key": key,
                             "value_index": 0, "page_stem": stem, "course_key": None, "status": status,
                             "value": res["value"], "raw_text": res["raw_text"],
                             "css_path": map_path(loc_["css_path"], cr_path) if loc_ else None,
                             "char_start": loc_.get("char_start"), "char_end": loc_.get("char_end")})
            code = next((r["value"] for r in rows if r["rule_id"] == CODE_RULE[loc["rule_id"]] and r["status"] == "found"), None)
            for r in rows:
                r["course_key"] = course_key(code)
            matches.extend(rows)
            occs.append({"occurrence_key": key, "page_stem": stem, "page_rule_id": page_rule,
                         "locator_rule_id": loc["rule_id"], "locator_rule_version": loc["version"],
                         "css_path": occ_path, "locator_index": index, "course_key": course_key(code)})
        if ld.get("repeat") and elements:
            uncovered.extend(_uncovered_codes(loc["rule_id"], elements, settings, cr_path))
    # page facts for the page signals
    codes = sorted(set(re.sub(r"\s", "", c) for c in re.findall(settings["signals"]["course_code_pattern"], text)))
    return {"stem": stem, "labels": labels, "occurrences": occs, "matches": matches,
            "has_content_root": main_html is not None, "codes": codes, "uncovered": uncovered}


def _uncovered_codes(locator_id: str, elements: list, settings: dict, cr_path: str) -> list[dict]:
    """Text that looks like a course code, inside the area where this locator found courses (their
    nearest common ancestor) but outside every found block: the `uncovered-code` signal."""
    from bs4 import NavigableString
    chain = list(elements[0].parents)
    area = next(a for a in chain if all(a in list(e.parents) for e in elements[1:]))
    found = set(map(id, elements))
    out = []
    for node in area.descendants:
        if not isinstance(node, NavigableString) or isinstance(node, PreformattedString):
            continue
        if any(id(p) in found for p in node.parents):
            continue
        for m in re.finditer(settings["signals"]["course_code_pattern"], str(node)):
            parent = node.parent
            pos = 0  # offset of this text node inside the parent's text (engine.text_of semantics)
            for d in parent.descendants:
                if d is node:
                    break
                if isinstance(d, Tag) and d.name == "br":
                    pos += 1
                elif isinstance(d, NavigableString) and not isinstance(d, PreformattedString):
                    pos += len(d)
            line = re.sub(r"\s+", " ", engine.text_of(parent)).strip()
            out.append({"locator": locator_id, "code": m.group(0), "css_path": map_path(engine.css_path(parent), cr_path),
                        "char_start": pos + m.start(), "char_end": pos + m.end(), "line": line[:160]})
    return out


def _check_run_page(args) -> int:
    """Equivalence check: our loop vs engine.run_page on the same page. Returns mismatches."""
    stem, url = args
    rules, settings = _W["rules"], _W["settings"]
    v2 = to_v2(rules, settings)
    html = (V2_RUN / "pages" / f"{stem}.html").read_text(errors="replace")
    from review_ui.runs import split_page
    main_html, _ = split_page(html, settings["content_root"])
    ref = engine.run_page(v2, url, main_html)
    ours = _extract_page(args)
    a = sorted((f["rule_id"], f["value"]) for e in ref["entities"] for f in e["fields"])
    b = sorted((m["rule_id"], m["value"]) for m in ours["matches"])
    return int(a != b)


def to_v2(rules: dict, settings: dict) -> dict:
    loc = {r["rule_id"]: r for r in rules.values() if r["kind"] == "locator"}
    return {"content_root": settings["content_root"], "page_title": settings["page_title"],
            "label_rules": [v2_label_rule(r) for r in rules.values() if r["kind"] == "page"],
            "field_rules": [v2_field_rule(r, loc[r["definition"]["locator"]]) for r in rules.values() if r["kind"] == "field"]}


def load_ruleset(version: int) -> tuple[dict, dict[str, dict]]:
    rs = json.loads((studio.catalog_dir() / "rulesets" / f"v{version:04d}.json").read_text())
    rules = {}
    for entry in rs["rules"]:
        path = studio.catalog_dir() / "rules" / entry["rule_id"] / f"v{entry['version']:04d}.json"
        rules[entry["rule_id"]] = json.loads(path.read_text())
    return rs, rules


# --- signals ----------------------------------------------------------------------------
def shape(value: str) -> str:
    s = re.sub(r"[A-Za-z]+", "A", value)
    return re.sub(r"\d+", "9", s)


def compute_signals(matches: list[dict], occs: list[dict], page_facts: list[dict], labels: list[dict],
                    rules: dict, settings: dict, only_rules: set[str] | None = None) -> list[dict]:
    sig = settings["signals"]
    out = []

    def add(kind, rule_id, occ, page, name, severity, detail, vi=0, where=None):
        out.append({"target_kind": kind, "rule_id": rule_id, "occurrence_key": occ,
                    "value_index": vi if kind == "match" else None, "page_stem": page, "signal": name,
                    "severity": severity, "detail": detail, **(where or {"css_path": None, "char_start": None, "char_end": None})})

    by_rule = defaultdict(list)
    for m in matches:
        by_rule[m["rule_id"]].append(m)
    for rid, rows in by_rule.items():
        if only_rules is not None and rid not in only_rules:
            continue
        rtype = rules[rid]["definition"]["rule_type"]
        derived = rtype in ("constant", "source_url")
        found = [r for r in rows if r["status"] == "found"]
        for r in rows:
            if r["status"] != "found":
                add("match", rid, r["occurrence_key"], r["page_stem"], "empty", "high",
                    "selector matched no element" if r["status"] == "no_match" else "element found, no value")
        if derived or not found:
            continue
        shapes = Counter(shape(r["value"]) for r in found)
        # A shape outlier only means something when the rule has a dominant shape (codes, not titles).
        short = shapes.most_common(1)[0][1] / len(found) >= 0.5
        lens = sorted(len(r["value"]) for r in found)
        lo = lens[max(0, int(len(lens) * sig["length_outlier_percentiles"][0] / 100) - 1)]
        hi = lens[min(len(lens) - 1, int(len(lens) * sig["length_outlier_percentiles"][1] / 100))]
        by_value = defaultdict(set)
        for r in found:
            by_value[re.sub(r"\s+", " ", r["value"]).strip().lower()].add(r["course_key"])
        for r in found:
            v = r["value"]
            if short and shapes[shape(v)] / len(found) < sig["shape_outlier_max_share"]:
                add("match", rid, r["occurrence_key"], r["page_stem"], "shape-outlier", "medium",
                    f"shape '{shape(v)}' is {shapes[shape(v)]} of {len(found)} values; most common "
                    f"'{shapes.most_common(1)[0][0]}'")
            if len(lens) >= 50 and (len(v) < lo or len(v) > hi):
                add("match", rid, r["occurrence_key"], r["page_stem"], "length-outlier", "low",
                    f"{len(v)} chars; 1st–99th percentile is {lo}–{hi}")
            keys = by_value[re.sub(r"\s+", " ", v).strip().lower()]
            if len(keys) > 1:
                others = sorted(k for k in keys if k and k != r["course_key"])
                add("match", rid, r["occurrence_key"], r["page_stem"], "duplicate-value", "medium",
                    f"same value on {len(keys)} courses: " + ", ".join(others[:5]) + ("…" if len(others) > 5 else ""))
            if re.search(sig["label_text_pattern"], v, re.I):
                lab = re.search(sig["label_text_pattern"], v, re.I).group(0).strip()
                add("match", rid, r["occurrence_key"], r["page_stem"], "contains-label-text", "high",
                    f"value includes the label text '{lab}'")
            if "\u00a0" in v or "&nbsp;" in v or re.search(r"<[a-z/][^>]*>", v):
                add("match", rid, r["occurrence_key"], r["page_stem"], "markup-leak", "low",
                    "non-breaking space or markup in the value")
    if only_rules is None:  # occurrence and page signals belong to locators/page rules
        per_page_key = Counter((o["page_stem"], o["course_key"], o["locator_rule_id"]) for o in occs)
        for o in occs:
            if o["course_key"] is None:
                add("occurrence", o["locator_rule_id"], o["occurrence_key"], o["page_stem"], "no-course-key",
                    "high", "the Coded Notation rule found nothing in this occurrence")
            elif per_page_key[(o["page_stem"], o["course_key"], o["locator_rule_id"])] > 1:
                add("occurrence", o["locator_rule_id"], o["occurrence_key"], o["page_stem"], "duplicate-record",
                    "medium", f"{o['course_key']} occurs {per_page_key[(o['page_stem'], o['course_key'], o['locator_rule_id'])]}× on this page")
        matched = defaultdict(set)
        for l in labels:
            if l["matched"]:
                matched[l["page_stem"]].add(l["rule_id"])
        occ_keys = defaultdict(set)
        for o in occs:
            occ_keys[o["page_stem"]].add(o["course_key"])
        for f in page_facts:
            stem = f["stem"]
            if not f["has_content_root"]:
                add("page", None, None, stem, "no-content-root", "medium",
                    f"content_root {settings['content_root']} not found on the page")
            if not matched[stem] and len(f["codes"]) >= sig["missed_page_min_codes"]:
                add("page", None, None, stem, "page-not-classified", "medium",
                    f"no page rule matched, but the page names {len(f['codes'])} course codes "
                    f"({', '.join(f['codes'][:4])}…): possible missed page")
            if "course-page" in matched[stem] and not occ_keys[stem]:
                add("page", "course-page", None, stem, "zero-records-on-course-page", "high", "course page without a course")
            for u in f.get("uncovered", []):
                add("page", u["locator"], None, stem, "uncovered-code", "medium",
                    f"'{u['code']}' in “{u['line']}” is outside every course this rule found: possible missed course",
                    where={"css_path": u["css_path"], "char_start": u["char_start"], "char_end": u["char_end"]})
    return out


def write_extraction(ext: str, labels, occs, matches, signals, meta: dict) -> dict:
    d = studio.extraction_dir(ext)
    key = lambda *cols: (lambda r: tuple("" if r[c] is None else r[c] for c in cols))  # noqa: E731
    counts = {
        "page_labels": write_parquet(d / "page_labels.parquet", sorted(labels, key=key("page_stem", "rule_id")), LABELS_SCHEMA),
        "occurrences": write_parquet(d / "occurrences.parquet", sorted(occs, key=key("occurrence_key")), OCC_SCHEMA),
        "matches": write_parquet(d / "matches.parquet", sorted(matches, key=key("rule_id", "occurrence_key", "value_index")), MATCH_SCHEMA),
        "signals": write_parquet(d / "signals.parquet", sorted(signals, key=key("target_kind", "rule_id", "occurrence_key", "page_stem", "signal")), SIGNAL_SCHEMA),
    }
    files = {f"{t}.parquet": {"rows": n, "sha256": hashlib.sha256((d / f"{t}.parquet").read_bytes()).hexdigest()}
             for t, n in counts.items()}
    write_json(d / "extraction.json", {**meta, "files": files})
    return counts


@step("extract rs-0001")
def step_extract(pool) -> dict:
    rs, rules = load_ruleset(1)
    settings = rs["settings"]
    pages = pq.read_table(studio.crawl_dir() / "pages.parquet").to_pylist()
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=min(10, os.cpu_count() or 4), initializer=_init_worker,
                             initargs=(rules, settings, None)) as ppool:
        results = list(ppool.map(_extract_page, [(p["page_stem"], p["url"]) for p in pages], chunksize=8))
        sample = [(p["page_stem"], p["url"]) for p in pages[:: max(1, len(pages) // 60)]]
        mismatches = sum(ppool.map(_check_run_page, sample))
    t_pages = time.perf_counter() - t0
    labels = [l for r in results for l in r["labels"]]
    occs = [o for r in results for o in r["occurrences"]]
    matches = [m for r in results for m in r["matches"]]
    t1 = time.perf_counter()
    signals = compute_signals(matches, occs, results, labels, rules, settings)
    t_sig = time.perf_counter() - t1
    meta = {"catalog": CATALOG, "crawl": CRAWL, "extraction": "rs-0001", "ruleset_version": 1,
            "parent_extraction": None, "created_at": NOW, "created_by": "golden-datasets extract",
            "engine": {"name": "review-ui-v2 engine primitives (read-only import)", "css_path_anchor": "document root"},
            "rerun_rules": [e["rule_id"] for e in rs["rules"]], "copied_rules": [],
            "pages_total": len(results), "pages_without_content_root": sum(not r["has_content_root"] for r in results),
            "run_page_equivalence_check": {"pages": len(sample), "mismatches": mismatches}}
    counts = write_extraction("rs-0001", labels, occs, matches, signals, meta)
    return {**counts, "parse_and_rules_s": round(t_pages, 1), "signals_s": round(t_sig, 2),
            "run_page_mismatches": f"{mismatches}/{len(sample)}"}


# ---------------------------------------------------------------------------------------
# Step: import-v2 annotations (Jared's 2026-10-19 session)
# ---------------------------------------------------------------------------------------
IN_SCOPE = {"Coded Notation", "External Identifier", "Learning Opportunity Name", "Description",
            "Subject Webpage", "Learning Type", "Life Cycle Status Type", "Language"}


def _norm(v: str | None) -> str:
    return re.sub(r"\s+", " ", v or "").strip().lower()


def locate_expected(page_stem: str, css: str, expected: str) -> dict:
    """Find the expected text inside the element at css_path; return offsets + a quote with context.
    Offsets are in the element's text (engine.text_of semantics, as for matches)."""
    html = (V2_RUN / "pages" / f"{page_stem}.html").read_text(errors="replace")
    doc = lxml.html.fromstring(html)
    found = doc.cssselect(css)
    out = {"text": expected, "css_path": None, "char_start": None, "char_end": None, "quote": None,
           "located_by": "not found on page"}
    if not found:
        return out
    soup = BeautifulSoup(lxml.html.tostring(found[0], encoding="unicode"), "lxml")
    text = engine.text_of(soup.body.contents[0])
    # whitespace-insensitive search: build a regex from the expected words
    words = expected.split()
    pattern = r"\s+".join(re.escape(w) for w in words)
    m = re.search(pattern, text)
    if not m:
        return out
    a, b = m.span()
    out.update(css_path=css, char_start=a, char_end=b, located_by="golden-datasets import-v2 text search",
               quote={"prefix": text[max(0, a - 30):a], "exact": text[a:b] if b - a <= 120 else text[a:a + 60] + "…" + text[b - 60:b],
                      "suffix": text[b:b + 30]})
    return out


@step("import-v2 annotations")
def step_annotations() -> dict:
    sess = V2_RUN / "review-ui" / V2_SESSION
    decisions = json.loads((sess / "decisions.json").read_text())
    notes = json.loads((sess / "notes.json").read_text())
    flags = json.loads((sess / "flags.json").read_text())
    pages = {p["url"]: p["page_stem"] for p in pq.read_table(studio.crawl_dir() / "pages.parquet").to_pylist()}
    E = studio.extraction_dir("rs-0001")
    matches = pq.read_table(E / "matches.parquet").to_pylist()
    occs = pq.read_table(E / "occurrences.parquet").to_pylist()
    m_by = {(m["rule_id"], m["page_stem"], m["course_key"]): m for m in matches}
    o_by = {(o["page_stem"], o["course_key"]): o for o in occs}
    _, rules = load_ruleset(1)
    rule_for = {(r["property_label"], r["definition"]["locator"]): rid for rid, r in rules.items() if r["kind"] == "field"}
    page_rule_id = {v2: v3 for v2, (v3, _, _) in PAGE_RULES.items()}
    notes_by_target = defaultdict(list)
    for n in notes:
        notes_by_target[n["target"]].append(n)

    stats = Counter()
    out = []

    def base(dec_at, author, imported):
        aid = "an-" + hashlib.sha1(canon(imported).encode()).hexdigest()[:12]
        return {"annotation_id": aid, "type": "verdict", "at": iso(dec_at), "author": author,
                "catalog": CATALOG, "crawl": CRAWL}

    def target_for(kind, rule_id, stem, ck, value_seen=None):
        occ = o_by.get((stem, ck)) if ck else None
        return {"kind": kind, "rule_id": rule_id, "rule_version_seen": rules[rule_id]["version"] if rule_id else None,
                "extraction_seen": "rs-0001", "occurrence_key": occ["occurrence_key"] if occ else None,
                "course_key": ck, "page_stem": stem, "value_index": 0 if kind == "match" else None,
                "value_seen": value_seen}

    # group field decisions by (record, label, url): reject + missing pair into one "wrong"
    groups = defaultdict(list)
    for key, d in decisions.items():
        if d["kind"] == "field":
            groups[(d["record_id"], d["canonical_label"], d["source_url"])].append((key, d))
    for (rec, label, url), items in groups.items():
        if label not in IN_SCOPE:
            stats["skipped_out_of_scope_field"] += len(items)
            continue
        stem = pages[url]
        occ = o_by[(stem, rec)]
        rule_id = rule_for[(label, occ["locator_rule_id"])]
        match = m_by[(rule_id, stem, rec)]
        by_status = defaultdict(list)
        for key, d in items:
            by_status[d["status"]].append((key, d))
        for key, d in by_status.get("accepted", []):
            if d["rule_id"] != rule_id or _norm(d["value"]) != _norm(match["value"]):
                stats["accepted_value_mismatch"] += 1
            imported = {"source": "review-ui-v2", "session": V2_SESSION, "decisions": [
                {"key": key, "status": "accepted", "author": d["author"], "seq": d["seq"],
                 "carried_from": d.get("carried_from")}]}
            note = " ".join(n["text"] for n in notes_by_target.get(key, []))
            imported["notes"] = [n["id"] for n in notes_by_target.get(key, [])]
            out.append({**base(d["at"], d["author"], imported), "target": target_for("match", rule_id, stem, rec, d["value"]),
                        "verdict": "correct", "expected": None, "note": note or None, "supersedes": None,
                        "imported_from": imported})
            stats["correct"] += 1
        rejected, missing = by_status.get("rejected", []), by_status.get("missing", [])
        if rejected:
            (rkey, r), mpair = rejected[0], (missing[0] if missing else None)
            decs = [{"key": rkey, "status": "rejected", "author": r["author"], "seq": r["seq"]}]
            expected = None
            if mpair:
                mkey, md = mpair
                decs.append({"key": mkey, "status": "missing", "author": md["author"], "seq": md["seq"]})
                # author rule: the wrong verdict belongs to whoever rejected; the expected text to whoever typed it
                expected = {**locate_expected(stem, match["css_path"], md["expected_value"]), "author": md["author"]}
            nts = notes_by_target.get(rkey, [])
            imported = {"source": "review-ui-v2", "session": V2_SESSION, "decisions": decs, "notes": [n["id"] for n in nts]}
            out.append({**base(r["at"], r["author"], imported), "target": target_for("match", rule_id, stem, rec, r["value"]),
                        "verdict": "wrong", "expected": expected, "note": " ".join(n["text"] for n in nts) or None,
                        "supersedes": None, "imported_from": imported})
            stats["wrong (reject + missing joined)" if mpair else "wrong"] += 1
            missing = missing[1:]
        for mkey, md in missing:
            imported = {"source": "review-ui-v2", "session": V2_SESSION,
                        "decisions": [{"key": mkey, "status": "missing", "author": md["author"], "seq": md["seq"]}]}
            out.append({**base(md["at"], md["author"], imported), "target": target_for("match", rule_id, stem, rec, None),
                        "verdict": "missing", "expected": {**locate_expected(stem, occ["css_path"], md["expected_value"]), "author": md["author"]},
                        "note": None, "supersedes": None, "imported_from": imported})
            stats["missing"] += 1
    for key, d in decisions.items():
        if d["kind"] != "label":
            continue
        if d.get("rule_id") not in page_rule_id:
            stats["skipped_label_without_page_rule"] += 1  # 'missing' Credential/Competency labels
            continue
        stem = pages[d["source_url"]]
        rid = page_rule_id[d["rule_id"]]
        verdict = {"accepted": "correct", "rejected": "wrong"}[d["status"]]
        imported = {"source": "review-ui-v2", "session": V2_SESSION, "decisions": [
            {"key": key, "status": d["status"], "author": d["author"], "seq": d["seq"], "reasons": d.get("reasons")}]}
        out.append({**base(d["at"], d["author"], imported), "target": target_for("page", rid, stem, None, d["value"]),
                    "verdict": verdict, "expected": None, "note": None, "supersedes": None, "imported_from": imported})
        stats[f"page rule {verdict}"] += 1
    for tkey, f in flags.items():
        if f["scope"] != "page" or not f.get("flagged"):
            stats["skipped_flag"] += 1
            continue
        imported = {"source": "review-ui-v2", "session": V2_SESSION, "flag": tkey, "seq": f["seq"]}
        out.append({**base(f["at"], f["author"], imported), "target": target_for("page", None, f["stem"], None),
                    "verdict": "question", "expected": None, "note": f.get("note") or None, "supersedes": None,
                    "imported_from": imported})
        stats["question (page flag)"] += 1
    for n in notes:
        if not any(n["id"] in (a["imported_from"].get("notes") or []) for a in out):
            stats["skipped_note_out_of_scope"] += 1
    # constant and URL rules start approved (spec §4.3)
    for rid, r in sorted(rules.items()):
        if r["kind"] == "field" and r["definition"]["rule_type"] in ("constant", "source_url"):
            imported = {"source": "golden-datasets import-v2", "rule": rid}
            out.append({"annotation_id": "ap-" + hashlib.sha1(canon(imported).encode()).hexdigest()[:12],
                        "type": "approve", "at": NOW, "author": "golden-datasets import-v2", "catalog": CATALOG, "crawl": None,
                        "target": {"kind": "rule", "rule_id": rid, "rule_version_seen": 1, "extraction_seen": None,
                                   "occurrence_key": None, "course_key": None, "page_stem": None,
                                   "value_index": None, "value_seen": None},
                        "verdict": None, "expected": None,
                        "note": "Constant / page-URL rule: approved on import (spec §4.3).",
                        "supersedes": None, "imported_from": imported})
            stats["approve (constant/URL rule)"] += 1
    out.sort(key=lambda a: (a["at"], a["annotation_id"]))
    path = studio.catalog_dir() / "annotations.jsonl"
    path.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in out))
    return {"annotations": len(out), **dict(stats)}


# ---------------------------------------------------------------------------------------
# Step: publish course-description v2 -> ruleset v2 -> extraction rs-0002 (rerun scope §4.3)
# ---------------------------------------------------------------------------------------
@step("publish course-description v2 + extract rs-0002")
def step_v2() -> dict:
    rs1, rules = load_ruleset(1)
    old = rules["course-description"]
    new = json.loads(json.dumps(old))
    new.update(version=2, parent_version=1, what=DESCRIPTION_V2["what"], how=DESCRIPTION_V2["how"],
               why=DESCRIPTION_V2["why"], examples=DESCRIPTION_V2["examples"],
               published_by="Claude Code (Eric's laptop) via golden-datasets rule publish", published_at=NOW)
    new.pop("imported_from", None)
    new["definition"].update(DESCRIPTION_V2["definition_patch"])
    rules["course-description"] = new
    new["content_hash"] = rule_hash("course-description", rules)
    # the declared examples must pass before publishing (what `golden-datasets rule try` checks first)
    for ex in new["examples"]:
        v, _, _ = engine.extract_from_text({"properties": {k: v for k, v in new["definition"].items()}}, ex["input"])
        v = engine.apply_transforms(v or "", []) if v else ""
        assert v == ex["output"], (v, ex)
    write_rule(new)
    rs2 = ruleset_doc(2, rules, rs1["settings"], 1, ["course-description"],
                      "course-description v2: drop leading requisite lines (Jared's 5 'wrong' descriptions).",
                      "Claude Code (Eric's laptop) via golden-datasets rule publish")
    write_json(studio.catalog_dir() / "rulesets" / "v0002.json", rs2)

    # Rerun scope: a changed field rule reruns itself + the code rule (for course_key); rest is copied.
    rerun = ["course-description", CODE_RULE[new["definition"]["locator"]]]
    E1 = studio.extraction_dir("rs-0001")
    labels1 = pq.read_table(E1 / "page_labels.parquet").to_pylist()
    occs1 = pq.read_table(E1 / "occurrences.parquet").to_pylist()
    matches1 = pq.read_table(E1 / "matches.parquet").to_pylist()
    signals1 = pq.read_table(E1 / "signals.parquet").to_pylist()
    page_rules = set(rules[new["definition"]["locator"]]["definition"]["page_rules"])
    stems = sorted({l["page_stem"] for l in labels1 if l["matched"] and l["rule_id"] in page_rules})
    url = {p["page_stem"]: p["url"] for p in pq.read_table(studio.crawl_dir() / "pages.parquet").to_pylist()}
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=min(10, os.cpu_count() or 4), initializer=_init_worker,
                             initargs=(rules, rs2["settings"], rerun)) as ppool:
        results = list(ppool.map(_extract_page, [(s, url[s]) for s in stems], chunksize=8))
    t_pages = time.perf_counter() - t0
    fresh = [m for r in results for m in r["matches"]]
    # the code rule did not change: its rerun must reproduce rs-0001 exactly (and the copy is kept)
    code1 = sorted((m["occurrence_key"], m["value"]) for m in matches1 if m["rule_id"] == rerun[1])
    code2 = sorted((m["occurrence_key"], m["value"]) for m in fresh if m["rule_id"] == rerun[1])
    assert code1 == code2, "code rule rerun differs from parent extraction"
    new_desc = [m for m in fresh if m["rule_id"] == "course-description"]
    matches2 = [m for m in matches1 if m["rule_id"] != "course-description"] + new_desc
    signals2 = [s for s in signals1 if s["rule_id"] != "course-description"] + compute_signals(
        new_desc, occs1, [], labels1, rules, rs2["settings"], only_rules={"course-description"})
    meta = {"catalog": CATALOG, "crawl": CRAWL, "extraction": "rs-0002", "ruleset_version": 2,
            "parent_extraction": "rs-0001", "created_at": NOW, "created_by": "golden-datasets rule publish",
            "engine": {"name": "review-ui-v2 engine primitives (read-only import)", "css_path_anchor": "document root"},
            "rerun_rules": rerun, "rerun_pages": len(stems),
            "copied_rules": sorted(e["rule_id"] for e in rs2["rules"] if e["rule_id"] not in rerun),
            "copied_from": "rs-0001", "pages_total": len(url), "pages_without_content_root": 0}
    counts = write_extraction("rs-0002", labels1, occs1, matches2, signals2, meta)
    changed = sum(1 for a, b in zip(sorted((m["occurrence_key"], m["value"]) for m in matches1 if m["rule_id"] == "course-description"),
                                    sorted((m["occurrence_key"], m["value"]) for m in new_desc)) if a != b)
    return {**counts, "rerun_pages": len(stems), "rerun_s": round(t_pages, 1), "descriptions_changed": changed,
            "descriptions_empty_now": sum(m["status"] != "found" for m in new_desc)}


# ---------------------------------------------------------------------------------------
# Step: a tiny golden publication (per-page golden JSON in the xtra-golden-sets-verified shape + lineage.parquet)
# ---------------------------------------------------------------------------------------
LINEAGE_SCHEMA = pa.schema([
    ("publication", pa.string()), ("golden_id", pa.string()), ("page_stem", pa.string()), ("property", pa.string()),
    ("ctdl_property", pa.string()), ("value_index", pa.int32()), ("extraction", pa.string()),
    ("rule_id", pa.string()), ("rule_version", pa.int32()), ("occurrence_key", pa.string()),
    ("match_value_index", pa.int32()), ("annotation_ids", pa.list_(pa.string())),
])
PUB = "pub-2026-10-26-avc-rs-0002-example"


@step("golden publication")
def step_golden() -> dict:
    _, rules = load_ruleset(2)
    E = studio.extraction_dir("rs-0002")
    matches = pq.read_table(E / "matches.parquet").to_pylist()
    pages = {p["page_stem"]: p for p in pq.read_table(studio.crawl_dir() / "pages.parquet").to_pylist()}
    anns = [json.loads(l) for l in (studio.catalog_dir() / "annotations.jsonl").read_text().splitlines()]
    decided = []
    for a in anns:
        ck = a["target"].get("course_key")
        if ck and ck not in decided and a["type"] == "verdict":
            decided.append(ck)
    full = defaultdict(list)
    for m in matches:
        if m["course_key"] and rules[m["rule_id"]]["definition"]["locator"] == "locator-course-page":
            full[m["course_key"]].append(m)
    stubbed = Counter(m["course_key"] for m in matches if m["rule_id"] == "stub-code")
    extra = [k for k, _ in stubbed.most_common() if k in full and k not in decided][:20 - len(decided)]
    chosen = decided + extra
    ann_by = defaultdict(list)
    for a in anns:
        t = a["target"]
        if t.get("rule_id") and t.get("occurrence_key"):
            ann_by[(t["rule_id"], t["occurrence_key"])].append(a["annotation_id"])
    lineage = []
    by_page = defaultdict(list)  # page_stem -> records, the shape of xtra-golden-sets-verified
    field_rules = sorted((r for r in rules.values() if r["kind"] == "field" and r["definition"]["locator"] == "locator-course-page"),
                         key=lambda r: ["Coded Notation", "External Identifier", "Learning Opportunity Name", "Description",
                                        "Subject Webpage", "Learning Type", "Life Cycle Status Type", "Language"].index(r["property_label"]))
    for ck in chosen:
        fields, stem = [], None
        for r in field_rules:
            m = next((m for m in full[ck] if m["rule_id"] == r["rule_id"]), None)
            if m is None or m["status"] != "found":
                continue
            stem = m["page_stem"]
            fields.append({"ctdl_property": r["ctdl_property"], "property": r["property_label"], "value": m["value"],
                           "source_url": pages[stem]["url"],
                           "location": ({"css_path": m["css_path"], "char_start": m["char_start"], "char_end": m["char_end"]}
                                        if m["css_path"] else None)})
            lineage.append({"publication": PUB, "golden_id": ck, "page_stem": stem, "property": r["property_label"],
                            "ctdl_property": r["ctdl_property"], "value_index": 0, "extraction": "rs-0002",
                            "rule_id": m["rule_id"], "rule_version": m["rule_version"],
                            "occurrence_key": m["occurrence_key"], "match_value_index": m["value_index"],
                            "annotation_ids": ann_by.get((m["rule_id"], m["occurrence_key"]), [])})
        by_page[stem].append({"golden_id": ck, "fields": fields})
    d = studio.crawl_dir() / "golden" / PUB
    for stem, records in by_page.items():  # one folder per page: <stem>/<stem>.json (+ the page as crawled)
        write_json(d / stem / f"{stem}.json", records)
        link = d / stem / f"{stem}.html"
        if not link.exists():
            link.symlink_to(V2_RUN / "pages" / f"{stem}.html")
    courses = [r for recs in by_page.values() for r in recs]
    write_parquet(d / "lineage.parquet", lineage, LINEAGE_SCHEMA)
    write_json(d / "publication.json", {
        "publication": PUB, "catalog": CATALOG, "crawl": CRAWL, "extraction": "rs-0002", "ruleset_version": 2,
        "published_at": NOW, "published_by": "make_example.py", "pages": len(by_page), "courses": len(courses), "lineage_rows": len(lineage),
        "format": "xtra-golden-sets-verified per-page shape: <stem>/<stem>.json = [{golden_id, fields: [{ctdl_property, property, "
                  "value, source_url, location}]}], plus <stem>/<stem>.html as crawled",
        "selection": f"the {len(decided)} courses with v2 verdicts + {len(extra)} courses that also appear on program pages",
        "approval_gate": {"all_rules_approved": False,
                          "note": "Example only. The real `golden-datasets golden publish` refuses until every rule version in the "
                                  "ruleset is approved; this one was written to show the format."}})
    return {"courses": len(courses), "lineage_rows": len(lineage)}


# ---------------------------------------------------------------------------------------
# Step: manifest
# ---------------------------------------------------------------------------------------
OTHER_CATALOGS = [
    ("ccsf-curricunet-com-catalog", "CCSF", "CurricUNET", "2026-10-01T16-02-34Z"),
    ("catalog-marshall-edu", "Marshall", "CourseLeaf", "2026-10-20T13-18-30Z"),
    ("catalog-ualr-edu", "UALR", "Acalog", "2026-10-18T21-05-00Z"),
    ("catalog-wvu-edu", "WVU", "CourseLeaf", "2026-10-20T13-19-46Z"),
]


@step("manifest")
def step_manifest() -> dict:
    rel = lambda p: str(Path(p).relative_to(ROOT))  # noqa: E731
    cdir, kdir = studio.catalog_dir(), studio.crawl_dir()
    exts = []
    for e in sorted((kdir / "extractions").iterdir()):
        meta = json.loads((e / "extraction.json").read_text())
        exts.append({"extraction": e.name, "ruleset_version": meta["ruleset_version"], "path": rel(e),
                     "parent_extraction": meta["parent_extraction"]})
    rulesets = [{"version": int(p.stem[1:]), "path": rel(p)} for p in sorted((cdir / "rulesets").glob("v*.json"))]
    avc = {
        "catalog": CATALOG, "name": "AVC", "platform": "eLumen", "status": "ready",
        "rule_versions": [rel(p) for p in sorted((cdir / "rules").glob("*/v*.json"))],
        "rulesets": rulesets, "annotations": rel(cdir / "annotations.jsonl"),
        "crawls": [{"crawl": CRAWL, "crawl_json": f"{CATALOG}/{CRAWL}/crawl.json", "pages_dir": f"{CATALOG}/{CRAWL}/pages",
                    "pages": rel(kdir / "pages.parquet"), "page_count": pq.read_metadata(kdir / "pages.parquet").num_rows,
                    "assets": {"assets": rel(kdir / "assets" / "assets.parquet"),
                               "page_assets": rel(kdir / "assets" / "page_assets.parquet"),
                               "files": rel(kdir / "assets" / "files")},
                    "extractions": exts,
                    "golden": [{"publication": g.name, "path": rel(g)} for g in sorted((kdir / "golden").iterdir())]}],
    }
    cats = [avc]
    for folder, name, platform, crawl in OTHER_CATALOGS:
        pages_dir = MIRROR / folder / crawl / "pages"
        n = sum(1 for p in os.scandir(pages_dir) if p.name.endswith(".html")) if pages_dir.exists() else None
        cats.append({"catalog": folder, "name": name, "platform": platform, "status": "not imported",
                     "rule_versions": [], "rulesets": [], "annotations": None,
                     "crawls": [{"crawl": crawl, "page_count": n, "extractions": [], "golden": []}]})
    write_json(ROOT / STUDIO / "manifest.json", {"schema": "golden-datasets-manifest/1", "updated_at": NOW, "catalogs": cats})
    return {"catalogs": len(cats)}



def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--steps", nargs="*", default=None, help="run only these steps (debugging)")
    args = ap.parse_args()
    want = lambda s: args.steps is None or s in args.steps  # noqa: E731
    if args.steps is None and ROOT.exists():
        shutil.rmtree(ROOT)  # the example is rebuilt from scratch every time
    ROOT.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=min(10, os.cpu_count() or 4)) as pool:
        if want("init"):
            step_init(pool)
        if want("assets"):
            step_assets(pool, fetch=not args.no_fetch)
    if want("rules"):
        step_rules()
    if want("extract"):
        step_extract(None)
    if want("annotations"):
        step_annotations()
    if want("v2"):
        step_v2()
    if want("golden"):
        step_golden()
    step_manifest()
    write_json(studio.SCRATCH / "timings.json", TIMINGS)


if __name__ == "__main__":
    main()
