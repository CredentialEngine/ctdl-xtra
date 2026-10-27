"""Throwaway prototype server for CTDL Golden Dataset Studio.

Answers JSON by querying the example files with DuckDB (no database file), serves the cleaned
saved pages for the page pane, and the static frontend. Annotations made in the UI are appended
to a scratch JSONL (never to the example root), and unioned with the real log in queries.

    GOLDEN_DATASETS_ROOT=… python server.py --port 8765
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
import threading
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin

import lxml.html
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import studio  # noqa: E402
from studio import ROOT  # noqa: E402

UI_LOG = studio.SCRATCH / "ui-annotations.jsonl"  # UI writes go here, not into the example root
LOCK = threading.Lock()
app = FastAPI(title="CTDL Golden Dataset Studio (prototype)")
CON = None
MAN: dict = {}
SEVERITY = {"high": 3, "medium": 2, "low": 1, "info": 0}
PROPERTY_ORDER = ["Coded Notation", "External Identifier", "Learning Opportunity Name", "Description",
                  "Subject Webpage", "Learning Type", "Life Cycle Status Type", "Language"]


def norm(v) -> str:
    return re.sub(r"\s+", " ", v or "").strip().lower()


def q(sql: str, params: list | None = None) -> list[dict]:
    with LOCK:
        cur = CON.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def setup() -> None:
    global CON, MAN
    CON = studio.connect()
    MAN = studio.manifest()
    UI_LOG.write_text("")
    CON.execute(f"""CREATE OR REPLACE VIEW ui_annotations AS SELECT * FROM read_json('{UI_LOG}',
        format='newline_delimited', columns={{'annotation_id':'VARCHAR','type':'VARCHAR','at':'VARCHAR',
        'author':'VARCHAR','catalog':'VARCHAR','crawl':'VARCHAR','target':'STRUCT(kind VARCHAR, rule_id VARCHAR,
        rule_version_seen INTEGER, extraction_seen VARCHAR, occurrence_key VARCHAR, course_key VARCHAR,
        page_stem VARCHAR, value_index INTEGER, value_seen VARCHAR)','verdict':'VARCHAR',
        'expected':'STRUCT(text VARCHAR, css_path VARCHAR, char_start INTEGER, char_end INTEGER,
        quote STRUCT(prefix VARCHAR, exact VARCHAR, suffix VARCHAR), located_by VARCHAR, author VARCHAR)',
        'note':'VARCHAR','supersedes':'VARCHAR','imported_from':'JSON'}})""")
    CON.execute("CREATE OR REPLACE VIEW all_annotations AS SELECT * FROM annotations UNION ALL BY NAME SELECT * FROM ui_annotations")
    CON.execute("""CREATE OR REPLACE VIEW latest_verdicts AS SELECT * FROM all_annotations WHERE type = 'verdict'
        QUALIFY row_number() OVER (PARTITION BY target.kind, target.rule_id, target.occurrence_key,
        target.page_stem, target.value_index ORDER BY "at" DESC, annotation_id DESC) = 1""")


def cat_info(catalog: str) -> dict:
    for c in MAN["catalogs"]:
        if c["catalog"] == catalog:
            return c
    raise HTTPException(404, "unknown catalog")


def ruleset(version: int) -> dict:
    return json.loads((studio.catalog_dir() / "rulesets" / f"v{version:04d}.json").read_text())


def rule_version(rule_id: str, version: int) -> dict:
    p = studio.catalog_dir() / "rules" / rule_id / f"v{version:04d}.json"
    if not p.exists():
        raise HTTPException(404, "unknown rule version")
    return json.loads(p.read_text())


def extraction_for(rs_version: int) -> str:
    for e in cat_info(studio.CATALOG)["crawls"][0]["extractions"]:
        if e["ruleset_version"] == rs_version:
            return e["extraction"]
    raise HTTPException(404, "no extraction for ruleset")


def latest_rs() -> int:
    return max(r["version"] for r in cat_info(studio.CATALOG)["rulesets"])


def rs_for_rule_version(rule_id: str, version: int) -> int:
    """Latest ruleset version that lists this rule version."""
    best = None
    for r in cat_info(studio.CATALOG)["rulesets"]:
        rs = ruleset(r["version"])
        if any(e["rule_id"] == rule_id and e["version"] == version for e in rs["rules"]):
            best = r["version"]
    return best


# ---------------------------------------------------------------------------------------- status
def rule_statuses(rs_version: int) -> dict[str, dict]:
    rs = ruleset(rs_version)
    ext = extraction_for(rs_version)
    out = {}
    approves = {(r["rule_id"], r["v"]) for r in q(
        "SELECT target.rule_id rule_id, target.rule_version_seen v FROM all_annotations WHERE type = 'approve'")}
    opens = q("""SELECT target.rule_id rule_id, target.rule_version_seen v, verdict, count(*) n
        FROM latest_verdicts GROUP BY ALL""")
    page_questions = q("SELECT count(*) n FROM latest_verdicts WHERE verdict = 'question' AND target.rule_id IS NULL")[0]["n"]
    fill = {r["rule_id"]: r for r in q(
        "SELECT rule_id, count(*) total, count(*) FILTER (status = 'found') found FROM matches WHERE extraction = ? GROUP BY 1", [ext])}
    pages = {r["rule_id"]: r for r in q(
        "SELECT rule_id, count(*) total, count(*) FILTER (matched) found FROM page_labels WHERE extraction = ? GROUP BY 1", [ext])}
    occ = {r["locator_rule_id"]: r["n"] for r in q(
        "SELECT locator_rule_id, count(*) n FROM occurrences WHERE extraction = ? GROUP BY 1", [ext])}
    reviewed = {r["rule_id"]: r["n"] for r in q("""SELECT target.rule_id rule_id, count(*) n FROM latest_verdicts
        WHERE verdict IN ('correct', 'wrong', 'missing', 'question') AND target.rule_id IS NOT NULL GROUP BY 1""")}
    sigs = {r["rule_id"]: r["n"] for r in q(
        "SELECT rule_id, count(*) n FROM signals WHERE extraction = ? AND rule_id IS NOT NULL GROUP BY 1", [ext])}
    for e in rs["rules"]:
        rv = rule_version(e["rule_id"], e["version"])
        mine = [o for o in opens if o["rule_id"] == e["rule_id"] and o["v"] == e["version"]]
        open_n = sum(o["n"] for o in mine if o["verdict"] in ("wrong", "missing", "question"))
        bad = sum(o["n"] for o in mine if o["verdict"] in ("wrong", "missing"))
        if (e["rule_id"], e["version"]) in approves:
            status = "approved"
        elif bad:
            status = "needs work"
        else:
            status = "in review"
        if e["kind"] == "field":
            f = fill.get(e["rule_id"], {"total": 0, "found": 0})
            fill_txt = f"{100 * f['found'] / f['total']:.0f}%" if f["total"] else "–"
            count = f["total"]
        elif e["kind"] == "page":
            f = pages.get(e["rule_id"], {"total": 0, "found": 0})
            fill_txt, count = f"{f['found']} pages", f["found"]
        else:
            fill_txt, count = f"{occ.get(e['rule_id'], 0)} courses", occ.get(e["rule_id"], 0)
        out[e["rule_id"]] = {
            "rule_id": e["rule_id"], "kind": e["kind"], "version": e["version"], "status": status,
            "fill": fill_txt, "count": count, "signals": sigs.get(e["rule_id"], 0), "open": open_n,
            "property": rv.get("property_label"), "ctdl": rv.get("ctdl_property"),
            "rule_type": rv["definition"].get("rule_type"), "what": rv["what"],
            "verdicts": {o["verdict"]: o["n"] for o in mine},
            "reviewed": reviewed.get(e["rule_id"], 0),
            "fill_detail": (f"{fill.get(e['rule_id'], {}).get('found', 0):,} of {fill.get(e['rule_id'], {}).get('total', 0):,} have a value"
                            if e["kind"] == "field" else None),
        }
    out["_meta"] = {"unclassified_pages": q(
        "SELECT count(*) n FROM signals WHERE extraction = ? AND signal = 'page-not-classified'", [ext])[0]["n"],
        "page_questions": page_questions}
    return out


# ---------------------------------------------------------------------------------------- API
@app.get("/api/catalogs")
def catalogs():
    out = []
    for c in MAN["catalogs"]:
        crawl = c["crawls"][0]
        logos = json.loads((HERE / "static" / "logos" / "sources.json").read_text())
        logo = logos.get(c["name"].lower())
        item = {"catalog": c["catalog"], "name": c["name"], "platform": c["platform"], "status": c["status"],
                "crawl": crawl["crawl"], "pages": crawl.get("page_count"),
                "logo": f"/static/logos/{logo['file']}" if logo else None, "logo_dark": bool(logo and logo.get("dark_bg"))}
        if c["status"] == "ready":
            rs = latest_rs()
            st = rule_statuses(rs)
            st.pop("_meta")
            item.update(ruleset=rs, extraction=extraction_for(rs), rules=len(st),
                        approved=sum(s["status"] == "approved" for s in st.values()),
                        needs_work=sum(s["status"] == "needs work" for s in st.values()),
                        annotations=q("SELECT count(*) n FROM all_annotations")[0]["n"],
                        courses=q("SELECT count(DISTINCT course_key) n FROM occurrences WHERE extraction = ?",
                                  [extraction_for(rs)])[0]["n"])
        out.append(item)
    return out


@app.get("/api/c/{catalog}/rules")
def rules(catalog: str, ruleset_version: int | None = None):
    cat_info(catalog)
    rs = ruleset_version or latest_rs()
    st = rule_statuses(rs)
    meta = st.pop("_meta")
    groups = {"page": [], "locator": [], "field": []}
    for s in st.values():
        groups[s["kind"]].append(s)
    order = {p: i for i, p in enumerate(PROPERTY_ORDER)}
    groups["field"].sort(key=lambda s: (s["rule_id"].startswith("stub"), order.get(s["property"], 99)))
    return {"ruleset": rs, "extraction": extraction_for(rs), "rulesets": [r["version"] for r in cat_info(catalog)["rulesets"]],
            "groups": groups, "meta": meta}


@app.get("/api/c/{catalog}/rules/{rule_id}")
def rule_detail(catalog: str, rule_id: str, version: int | None = None):
    """The Rules tab always shows the version in the latest ruleset; other versions live in Compare."""
    versions = sorted(int(p.stem[1:]) for p in (studio.catalog_dir() / "rules" / rule_id).glob("v*.json"))
    current = next(e["version"] for e in ruleset(latest_rs())["rules"] if e["rule_id"] == rule_id)
    v = version or current
    rv = rule_version(rule_id, v)
    rs = rs_for_rule_version(rule_id, v)
    st = rule_statuses(rs)[rule_id]
    term = (rv.get("ctdl_property") or "").split(":")[-1]
    crawl = studio.CRAWL
    return {"rule": rv, "versions": versions, "ruleset": rs, "extraction": extraction_for(rs), "status": st,
            "ctdl_url": f"https://credreg.net/ctdl/terms/{term}" if term else None,
            "crawl_date": f"{crawl[8:10]} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(crawl[5:7]) - 1]} {crawl[:4]}",
            "blocking": sum(n for k, n in st["verdicts"].items() if k in ("wrong", "missing"))}


def _signals_for(ext: str, rule_id: str, kind: str):
    rows = q("""SELECT occurrence_key, value_index, page_stem, signal, severity, detail FROM signals
        WHERE extraction = ? AND rule_id = ? AND target_kind = ?""", [ext, rule_id, kind])
    return rows


def _history(row: dict, ann: dict | None, version: int) -> tuple[str | None, list[dict]]:
    """Which verdict still applies to the current value, plus history signals (computed at query time)."""
    if not ann or ann["verdict"] == "cleared":
        return None, []
    same_value = norm(ann.get("value_seen")) == norm(row.get("value"))
    if ann["verdict"] in ("question",) or ann["rule_version_seen"] == version or same_value:
        hist = []
        if ann["rule_version_seen"] != version:
            hist.append({"signal": f"verdict carried from v{ann['rule_version_seen']}", "severity": "info",
                         "detail": "value unchanged since the verdict"})
        return ann["verdict"], hist
    if ann["verdict"] == "correct":
        return None, [{"signal": "changed-since-correct", "severity": "high",
                       "detail": f"{ann['author']} marked v{ann['rule_version_seen']}'s value correct; it changed"}]
    if ann.get("expected_text") and norm(ann["expected_text"]) == norm(row.get("value")):
        return None, [{"signal": "fixed-since-wrong", "severity": "info",
                       "detail": f"{ann['author']} marked v{ann['rule_version_seen']} {ann['verdict']}; value now equals the expected text"}]
    return None, [{"signal": "previously-wrong", "severity": "high",
                   "detail": f"{ann['author']} marked v{ann['rule_version_seen']} {ann['verdict']}"}]


def _ann_dict(a: dict) -> dict:
    return {k: a[k] for k in ("annotation_id", "verdict", "author", "at", "note", "rule_version_seen",
                              "value_seen", "expected_text", "expected_css", "expected_start", "expected_end", "imported")}


ANN_COLS = """a.annotation_id, a.verdict, a.author, a."at", a.note, a.target.rule_version_seen rule_version_seen,
    a.target.value_seen value_seen, a.expected.text expected_text, a.expected.css_path expected_css,
    a.expected.char_start expected_start, a.expected.char_end expected_end, a.imported_from IS NOT NULL imported"""


@app.get("/api/c/{catalog}/rules/{rule_id}/rows")
def rule_rows(catalog: str, rule_id: str, version: int | None = None, limit: int = 5000):
    d = rule_detail(catalog, rule_id, version)
    rv, ext, v = d["rule"], d["extraction"], d["rule"]["version"]
    kind = rv["kind"]
    if kind == "field":
        rows = q(f"""SELECT m.*, p.title, p.url, {ANN_COLS} FROM matches m JOIN pages p USING (page_stem)
            LEFT JOIN latest_verdicts a ON a.target.kind = 'match' AND a.target.rule_id = m.rule_id
            AND a.target.occurrence_key = m.occurrence_key AND a.target.value_index = m.value_index
            WHERE m.extraction = ? AND m.rule_id = ?""", [ext, rule_id])
        sigs = _signals_for(ext, rule_id, "match")
        key = lambda r: (r["occurrence_key"], r["value_index"])  # noqa: E731
    elif kind == "locator":
        rows = q(f"""SELECT o.occurrence_key, o.page_stem, o.course_key, o.css_path, o.locator_index,
            'found' status, o.course_key AS value, p.title, p.url, {ANN_COLS} FROM occurrences o JOIN pages p USING (page_stem)
            LEFT JOIN latest_verdicts a ON a.target.kind = 'occurrence' AND a.target.occurrence_key = o.occurrence_key
            WHERE o.extraction = ? AND o.locator_rule_id = ?""", [ext, rule_id])
        sigs = _signals_for(ext, rule_id, "occurrence") + _signals_for(ext, rule_id, "page")
        key = lambda r: r["occurrence_key"]  # noqa: E731
        for s in sigs:
            if s["occurrence_key"] is None:  # page signal: attach to the page's first occurrence
                first = next((r["occurrence_key"] for r in rows if r["page_stem"] == s["page_stem"]), None)
                s["occurrence_key"] = first
    else:  # page rule: matched pages, plus unmatched pages with a page signal
        rows = q(f"""SELECT l.page_stem, l.page_stem AS occurrence_key, l.matched, l.reason,
            CASE WHEN l.matched THEN 'found' ELSE 'no_match' END status,
            CASE WHEN l.matched THEN 'matched' ELSE 'not matched · ' || replace(l.reason, '_', ' ') END AS value,
            p.title, p.url, {ANN_COLS},
            u.note AS question_note, u.author AS question_author, u.verdict AS question_verdict
            FROM page_labels l JOIN pages p USING (page_stem)
            LEFT JOIN latest_verdicts a ON a.target.kind = 'page' AND a.target.rule_id = l.rule_id AND a.target.page_stem = l.page_stem
            LEFT JOIN latest_verdicts u ON u.target.kind = 'page' AND u.target.rule_id IS NULL AND u.target.page_stem = l.page_stem
            WHERE l.extraction = ? AND l.rule_id = ? AND (l.matched OR l.page_stem IN
              (SELECT page_stem FROM signals WHERE extraction = ? AND target_kind = 'page'))""", [ext, rule_id, ext])
        sigs = q("SELECT page_stem AS occurrence_key, page_stem, signal, severity, detail FROM signals "
                 "WHERE extraction = ? AND target_kind = 'page' AND (rule_id = ? OR rule_id IS NULL)", [ext, rule_id])
        key = lambda r: r["occurrence_key"]  # noqa: E731
    by = {}
    for s in sigs:
        by.setdefault((s["occurrence_key"], s.get("value_index") or 0) if kind == "field" else s["occurrence_key"], []).append(
            {"signal": s["signal"], "severity": s["severity"], "detail": s["detail"]})
    out = []
    for r in rows:
        ann = _ann_dict(r) if r.get("annotation_id") else None
        verdict, hist = _history(r, ann, v)
        if r.get("question_verdict") and not verdict:
            verdict = "question"
            ann = ann or {"verdict": "question", "note": r["question_note"], "author": r["question_author"]}
        if kind == "page" and r.get("question_verdict"):
            hist.append({"signal": "question-for-institution", "severity": "high", "detail": r["question_note"] or "flagged"})
        s = by.get(key(r), []) + hist
        score = sum(SEVERITY.get(x["severity"], 0) for x in s) + (3 if verdict in ("wrong", "missing", "question") else 0)
        score += 2 * sum(x["signal"] == "fixed-since-wrong" for x in s)  # history: Jared's rows come early
        out.append({
            "occurrence_key": r["occurrence_key"], "value_index": r.get("value_index", 0), "page_stem": r["page_stem"],
            "course_key": r.get("course_key"), "status": r["status"], "value": r.get("value"),
            "raw_text": r.get("raw_text"), "css_path": r.get("css_path"), "char_start": r.get("char_start"),
            "char_end": r.get("char_end"), "title": r["title"], "url": r["url"], "signals": s, "score": score,
            "verdict": verdict, "annotation": ann,
            "sample_order": hashlib.md5(r["occurrence_key"].encode()).hexdigest(),
        })
    comments = {}
    for c in q("""SELECT target.occurrence_key ok, target.page_stem ps, note, author FROM all_annotations
        WHERE type = 'comment' AND target.rule_id = ? QUALIFY row_number() OVER (PARTITION BY target.occurrence_key,
        target.page_stem ORDER BY "at" DESC) = 1""", [rule_id]):
        comments[c["ok"] or c["ps"]] = {"note": c["note"], "author": c["author"]}
    for r in out:
        r["comment"] = comments.get(r["occurrence_key"]) or comments.get(r["page_stem"])
    out.sort(key=lambda r: (-r["score"], r["sample_order"]))
    with_signals = sum(1 for r in out if r["score"] > 0)
    return {"rule": d["rule"], "versions": d["versions"], "status": d["status"], "extraction": ext,
            "total": len(out), "with_signals": with_signals, "rows": out[:limit],
            "signal_counts": _count_signals(out)}


def _count_signals(rows):
    c = {}
    for r in rows:
        for s in r["signals"]:
            c[s["signal"]] = c.get(s["signal"], 0) + 1
    return dict(sorted(c.items(), key=lambda x: -x[1]))


@app.get("/api/c/{catalog}/pages")
def pages_search(catalog: str, query: str = "", rule_id: str | None = None):
    """Saved pages by title or address, for "Add a page this rule missed"."""
    ext = extraction_for(latest_rs())
    return q("""SELECT p.page_stem, p.title, p.url, coalesce(l.matched, false) matched FROM pages p
        LEFT JOIN page_labels l ON l.page_stem = p.page_stem AND l.extraction = ? AND l.rule_id = ?
        WHERE p.title ILIKE ? OR p.url ILIKE ? ORDER BY matched, p.url LIMIT 8""", [ext, rule_id or "", f"%{query}%", f"%{query}%"])


@app.get("/api/c/{catalog}/pages/{stem}/uncovered")
def page_uncovered(catalog: str, stem: str, rule_id: str, extraction: str | None = None):
    """Course-code-looking text outside every block a locator found (the `uncovered-code` signal)."""
    ext = extraction or extraction_for(latest_rs())
    return q("""SELECT css_path, char_start, char_end, detail FROM signals WHERE extraction = ? AND page_stem = ?
        AND rule_id = ? AND signal = 'uncovered-code' ORDER BY css_path, char_start""", [ext, stem, rule_id])


@app.get("/api/c/{catalog}/occurrence")
def occurrence(catalog: str, key: str, extraction: str | None = None):
    """Every field match of one occurrence (for numbered highlights in the page pane)."""
    ext = extraction or extraction_for(latest_rs())
    return q("""SELECT m.rule_id, m.status, m.value, m.raw_text, m.css_path, m.char_start, m.char_end
        FROM matches m WHERE m.extraction = ? AND m.occurrence_key = ? ORDER BY m.rule_id""", [ext, key])


@app.get("/api/c/{catalog}/pages/{stem}/occurrences")
def page_occurrences(catalog: str, stem: str, extraction: str | None = None):
    ext = extraction or extraction_for(latest_rs())
    return q("SELECT occurrence_key, css_path, course_key, locator_rule_id FROM occurrences WHERE extraction = ? AND page_stem = ? ORDER BY locator_index",
             [ext, stem])


@app.get("/api/c/{catalog}/course-pages")
def course_pages(catalog: str, course_key: str, extraction: str | None = None):
    """Pages where a course occurs: the browser tabs of the page pane."""
    ext = extraction or extraction_for(latest_rs())
    return q("""SELECT o.page_stem, o.occurrence_key, o.css_path, o.locator_rule_id, p.title, p.url
        FROM occurrences o JOIN pages p USING (page_stem) WHERE o.extraction = ? AND o.course_key = ?
        ORDER BY o.locator_rule_id, p.url""", [ext, course_key])


# ---------------------------------------------------------------------------------------- records
@app.get("/api/c/{catalog}/courses")
def courses(catalog: str, query: str = "", extraction: str | None = None):
    ext = extraction or extraction_for(latest_rs())
    return q("""SELECT o.course_key, any_value(m.value) FILTER (m.rule_id IN ('course-name', 'stub-name')) AS name,
        count(DISTINCT o.page_stem) pages, bool_or(o.locator_rule_id = 'locator-course-page') has_course_page,
        count(a.annotation_id) annotations
        FROM occurrences o LEFT JOIN matches m USING (extraction, occurrence_key)
        LEFT JOIN latest_verdicts a ON a.target.course_key = o.course_key AND a.target.occurrence_key = o.occurrence_key
            AND a.target.rule_id = m.rule_id
        WHERE o.extraction = ? AND o.course_key ILIKE ? GROUP BY 1
        ORDER BY annotations DESC, o.course_key LIMIT 400""", [ext, f"%{query}%"])


@app.get("/api/c/{catalog}/courses/{course_key}")
def course(catalog: str, course_key: str, ruleset_version: int | None = None):
    rs = ruleset_version or latest_rs()
    ext = extraction_for(rs)
    rows = q(f"""SELECT m.*, o.locator_rule_id, p.title, p.url, {ANN_COLS} FROM matches m
        JOIN occurrences o USING (extraction, occurrence_key) JOIN pages p ON p.page_stem = m.page_stem
        LEFT JOIN latest_verdicts a ON a.target.kind = 'match' AND a.target.rule_id = m.rule_id
            AND a.target.occurrence_key = m.occurrence_key AND a.target.value_index = m.value_index
        WHERE m.extraction = ? AND o.course_key = ? ORDER BY o.locator_rule_id, p.url""", [ext, course_key])
    st = rule_statuses(rs)
    sigs = q("""SELECT s.rule_id, s.occurrence_key, s.signal, s.severity, s.detail FROM signals s
        JOIN occurrences o USING (extraction, occurrence_key) WHERE s.extraction = ? AND o.course_key = ?""", [ext, course_key])
    props = {}
    for r in rows:
        st_r = st[r["rule_id"]]
        ann = _ann_dict(r) if r.get("annotation_id") else None
        verdict, hist = _history(r, ann, st_r["version"])
        props.setdefault(st_r["property"], []).append({
            "rule_id": r["rule_id"], "rule_version": r["rule_version"], "rule_status": st_r["status"],
            "ctdl": st_r["ctdl"], "occurrence_key": r["occurrence_key"], "value_index": r["value_index"],
            "page_stem": r["page_stem"], "title": r["title"], "url": r["url"], "status": r["status"], "value": r["value"],
            "raw_text": r["raw_text"], "css_path": r["css_path"], "char_start": r["char_start"], "char_end": r["char_end"],
            "locator": r["locator_rule_id"], "verdict": verdict, "annotation": ann,
            "signals": [{"signal": s["signal"], "severity": s["severity"], "detail": s["detail"]} for s in sigs
                        if s["rule_id"] == r["rule_id"] and s["occurrence_key"] == r["occurrence_key"]] + hist})
    return {"course_key": course_key, "ruleset": rs, "extraction": ext,
            "properties": [{"property": p, "values": props[p]} for p in PROPERTY_ORDER if p in props]}


# ---------------------------------------------------------------------------------------- compare
def _words_diff(a: str | None, b: str | None) -> list[dict]:
    ta, tb = re.findall(r"\S+|\s+", a or ""), re.findall(r"\S+|\s+", b or "")
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=ta, b=tb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "eq", "text": "".join(ta[i1:i2])})
        else:
            if i2 > i1:
                out.append({"op": "del", "text": "".join(ta[i1:i2])})
            if j2 > j1:
                out.append({"op": "ins", "text": "".join(tb[j1:j2])})
    return out


@app.get("/api/c/{catalog}/compare")
def compare(catalog: str, a: int | None = None, b: int | None = None, scope: str = "all"):
    """Two ruleset versions on the same crawl, joined on (rule, occurrence key). Scope: all changed rules or one."""
    versions = sorted(r["version"] for r in cat_info(catalog)["rulesets"])
    b = b or versions[-1]
    a = a or (versions[-2] if len(versions) > 1 else versions[-1])
    ea, eb = extraction_for(a), extraction_for(b)
    rsa, rsb = ruleset(a), ruleset(b)
    va = {x["rule_id"]: x["version"] for x in rsa["rules"]}
    changed_rules = [e["rule_id"] for e in rsb["rules"] if va.get(e["rule_id"]) != e["version"]]
    in_scope = changed_rules if scope == "all" else [scope]
    rid_list = "', '".join(in_scope) or "-"
    all_list = "', '".join(changed_rules) or "-"
    per_rule = {r["rule_id"]: r["n"] for r in q(f"""SELECT rule_id, count(*) n FROM matches x JOIN matches y USING (rule_id, occurrence_key, value_index)
        WHERE x.extraction = ? AND y.extraction = ? AND rule_id IN ('{all_list}') AND x.value IS DISTINCT FROM y.value GROUP BY 1""", [ea, eb])}
    rules_meta = []
    for rid in changed_rules:
        rv = rule_version(rid, next(x["version"] for x in rsb["rules"] if x["rule_id"] == rid))
        rules_meta.append({"rule_id": rid, "term": rv.get("ctdl_property") or rv.get("property_label") or rid,
                           "property": rv.get("property_label"), "from": va.get(rid), "to": rv["version"],
                           "changed": per_rule.get(rid, 0), "why": rv["why"]})
    rows = q(f"""
        WITH ma AS (SELECT * FROM matches WHERE extraction = ? AND rule_id IN ('{rid_list}')),
             mb AS (SELECT * FROM matches WHERE extraction = ? AND rule_id IN ('{rid_list}'))
        SELECT coalesce(mb.rule_id, ma.rule_id) rule_id, coalesce(mb.occurrence_key, ma.occurrence_key) occurrence_key,
               coalesce(mb.course_key, ma.course_key) course_key, coalesce(mb.page_stem, ma.page_stem) page_stem,
               ma.value AS old_value, mb.value AS new_value,
               ma.occurrence_key IS NULL AS is_new, mb.occurrence_key IS NULL AS vanished
        FROM ma FULL OUTER JOIN mb USING (rule_id, occurrence_key, value_index)""", [ea, eb])
    by_key = {(r["rule_id"], r["occurrence_key"]): r for r in rows}
    anns = {(r["rule_id"], r["occurrence_key"]): r for r in q(f"""SELECT target.rule_id rule_id, target.occurrence_key occurrence_key,
        verdict, author, "at", note, target.rule_version_seen v, target.value_seen value_seen, expected.text expected_text
        FROM latest_verdicts WHERE target.kind = 'match' AND target.rule_id IN ('{rid_list}')""")}
    counts = {"changed": 0, "fixed": 0, "still wrong": 0, "newly wrong": 0, "unchanged": 0, "new": 0, "vanished": 0}
    decided, sample = [], []

    def rec(r):  # one record as the UI shows it
        changed = r["old_value"] != r["new_value"]
        return {"rule_id": r["rule_id"], "course_key": r["course_key"], "page_stem": r["page_stem"],
                "old_value": r["old_value"], "new_value": r["new_value"],
                "diff": _words_diff(r["old_value"], r["new_value"]) if changed else None}

    for r in rows:
        ann = anns.get((r["rule_id"], r["occurrence_key"]))
        changed = r["old_value"] != r["new_value"]
        key = "new" if r["is_new"] else "vanished" if r["vanished"] else "changed" if changed else "unchanged"
        counts[key] += 1
        if ann:
            if ann["verdict"] in ("wrong", "missing"):
                outcome = "fixed" if ann["expected_text"] and norm(ann["expected_text"]) == norm(r["new_value"]) else "still wrong"
            elif ann["verdict"] == "correct":
                outcome = "newly wrong" if changed else "still correct"
            else:
                outcome = "question"
            if outcome in counts:
                counts[outcome] += 1
            decided.append({**rec(r), "annotation": ann, "outcome": outcome})
        elif changed:
            sample.append(rec(r))
    order = {"fixed": 0, "still wrong": 1, "newly wrong": 2, "question": 3, "still correct": 4}
    decided.sort(key=lambda r: (order[r["outcome"]], r["course_key"] or ""))
    sample.sort(key=lambda r: hashlib.md5((r["rule_id"] + (r["course_key"] or "") + r["page_stem"]).encode()).hexdigest())
    sig = {}
    for ext, side in ((ea, "a"), (eb, "b")):
        for s_ in q(f"""SELECT signal, rule_id, occurrence_key FROM signals WHERE extraction = ? AND rule_id IN ('{rid_list}')
                AND target_kind = 'match'""", [ext]):
            sig.setdefault(s_["signal"], {"a": set(), "b": set()})[side].add((s_["rule_id"], s_["occurrence_key"]))
    signals = []
    for name, d in sorted(sig.items(), key=lambda kv: -(len(kv[1]["a"]) + len(kv[1]["b"]))):
        lost = [rec(by_key[k]) for k in sorted(d["a"] - d["b"]) if k in by_key]
        gained = [rec(by_key[k]) for k in sorted(d["b"] - d["a"]) if k in by_key]
        signals.append({"signal": name, "before": len(d["a"]), "after": len(d["b"]),
                        "lost": lost[:25], "lost_total": len(lost), "gained": gained[:25], "gained_total": len(gained)})
    return {"a": a, "b": b, "versions": versions, "scope": scope, "rules": rules_meta, "counts": counts,
            "signals": signals, "decided": decided, "sample": sample[:8], "sample_total": len(sample)}



# ---------------------------------------------------------------------------------------- prompt
def _short(v: str | None, n: int = 220) -> str:
    v = (v or "").replace("\n", "⏎ ")
    return v if len(v) <= n else v[: n - 1] + "…"


def build_prompt(scope: str) -> str:
    rs = latest_rs()
    ext = extraction_for(rs)
    st = rule_statuses(rs)
    st.pop("_meta")
    if scope == "needs-work":
        targets = [s for s in st.values() if s["status"] == "needs work"]
    else:
        targets = [st[scope]]
    crawl = studio.CRAWL
    L = []
    L.append(f"# Improve {'rule `' + targets[0]['rule_id'] + '`' if len(targets) == 1 else str(len(targets)) + ' rules that need work'} — AVC catalog")
    L.append("")
    L.append("You are improving the declarative extraction rules of **CTDL Golden Dataset Studio** for one catalog. "
             "A domain expert reviewed the extracted values and left annotations. Your job: change the rule(s) below "
             "so the annotated problems are fixed without breaking anything the expert marked correct, then publish "
             "a new version. Work only through the `golden-datasets` CLI; never edit files in the storage root yourself.")
    L.append("")
    L.append("## Context")
    L.append(f"- Catalog: `{studio.CATALOG}` (AVC, eLumen platform)")
    L.append(f"- Crawl: `{crawl}` — {MAN['catalogs'][0]['crawls'][0]['page_count']} saved pages")
    L.append(f"- Current ruleset: v{rs} (extraction `{ext}`)")
    L.append(f"- Storage root: `$GOLDEN_DATASETS_ROOT` (the Studio's root; `golden-datasets` reads it, caches pages locally)")
    L.append(f"- Page files: `$GOLDEN_DATASETS_ROOT/{studio.CATALOG}/{crawl}/pages/<page_stem>.html` (full saved page, scripts already ran at crawl time)")
    L.append("- Rule format: a field rule's `definition` has `locator`, `rule_type` (css / css+regex / constant / source_url), "
             "`selector` (CSS, evaluated inside one course occurrence), optional `regex` + `group`, `transforms` "
             "(strip, collapse_ws, upper, lower, remove_spaces, rstrip:<chars>), optional `map`.")
    L.append("")
    for t in targets:
        rv = rule_version(t["rule_id"], t["version"])
        L.append(f"## Rule `{t['rule_id']}` v{t['version']} — {t['kind']} rule"
                 + (f", {rv['property_label']} (`{rv['ctdl_property']}`)" if rv.get("property_label") else "")
                 + f" — status: **{t['status']}**")
        L.append("")
        L.append(f"- **what:** {rv['what']}")
        L.append(f"- **how:** {rv['how']}")
        L.append(f"- **why:** {rv['why'] or '(empty: imported from v2)'}")
        L.append(f"- depends on: {', '.join('`' + d + '`' for d in rv['depends_on']) or '—'}")
        L.append("")
        L.append("```json")
        L.append(json.dumps(rv["definition"], indent=2, ensure_ascii=False))
        L.append("```")
        L.append("")
        if t["kind"] == "page":
            anns = q(f"""SELECT a.verdict, a.author, a."at", a.note, a.target.page_stem page_stem, p.url, p.title
                FROM latest_verdicts a JOIN pages p ON p.page_stem = a.target.page_stem
                WHERE a.target.kind = 'page' AND (a.target.rule_id = ? OR (a.target.rule_id IS NULL AND a.target.page_stem IN
                  (SELECT page_stem FROM page_labels WHERE extraction = ? AND rule_id = ? AND matched)))
                ORDER BY CASE a.verdict WHEN 'wrong' THEN 0 WHEN 'missing' THEN 1 WHEN 'question' THEN 2 ELSE 3 END, p.url""",
                     [t["rule_id"], ext, t["rule_id"]])
        else:
            anns = q(f"""SELECT a.verdict, a.author, a."at", a.note, a.target.page_stem page_stem, a.target.course_key course_key,
                a.target.occurrence_key occurrence_key, a.target.value_seen value_seen, a.target.rule_version_seen v,
                a.expected.text expected_text, a.expected.css_path expected_css, a.expected.char_start es, a.expected.char_end ee,
                m.value current_value, m.css_path, p.url, p.title
                FROM latest_verdicts a JOIN pages p ON p.page_stem = a.target.page_stem
                LEFT JOIN matches m ON m.extraction = ? AND m.rule_id = a.target.rule_id AND m.occurrence_key = a.target.occurrence_key
                WHERE a.target.kind = 'match' AND a.target.rule_id = ?
                ORDER BY CASE a.verdict WHEN 'wrong' THEN 0 WHEN 'missing' THEN 1 WHEN 'question' THEN 2 ELSE 3 END, a.target.course_key""",
                     [ext, t["rule_id"]])
        c = {}
        anns = [dict(a_, verdict=("question for the institution" if a_["verdict"] == "question" else a_["verdict"])) for a_ in anns]
        for a_ in anns:
            c[a_["verdict"]] = c.get(a_["verdict"], 0) + 1
        L.append(f"### Annotations ({', '.join(f'{n} {k}' for k, n in c.items()) or 'none'})")
        L.append("")
        n = 0
        for a_ in anns:
            if a_["verdict"] == "correct":
                continue
            n += 1
            head = a_.get("course_key") or a_["title"]
            L.append(f"{n}. **{a_['verdict'].upper()}** — {head} — page `{a_['page_stem']}`")
            L.append(f"   - url: {a_['url']}")
            if t["kind"] == "field":
                L.append(f"   - extracted (v{a_['v']}): \"{_short(a_['value_seen'])}\"")
                if a_.get("expected_text"):
                    loc = ("" if not a_.get("expected_css") else
                           f" (chars {a_['es']}–{a_['ee']} of the extracted element)" if a_["expected_css"] == a_["css_path"]
                           else f" (chars {a_['es']}–{a_['ee']} of `…{a_['expected_css'].split(' > ', )[-1]}`)")
                    L.append(f"   - expected: \"{_short(a_['expected_text'])}\"{loc}")
                if a_.get("v") != t["version"]:
                    now = "equals the expected text (fixed)" if a_.get("expected_text") and norm(a_["expected_text"]) == norm(a_["current_value"]) \
                        else ("unchanged" if norm(a_["value_seen"]) == norm(a_["current_value"]) else f"\"{_short(a_['current_value'], 120)}\"")
                    L.append(f"   - current (v{t['version']}): {now}")
                L.append(f"   - look: `golden-datasets pages get {a_['page_stem']} --match {t['rule_id']} --text`")
            if a_.get("note"):
                L.append(f"   - note ({a_['author']}): \"{a_['note']}\"")
        correct = [a_ for a_ in anns if a_["verdict"] == "correct"]
        if correct:
            L.append("")
            L.append(f"**Marked correct — these values must not change ({len(correct)}):** "
                     + ", ".join(f"{a_.get('course_key') or a_['title']}" for a_ in correct))
            if t["kind"] == "field":
                for a_ in correct:
                    if re.search(r"(?i)^(advisory|limitation)", a_["value_seen"] or ""):
                        L.append(f"   - {a_['course_key']}: \"{_short(a_['value_seen'], 120)}\"")
        sig = q("SELECT signal, count(*) n FROM signals WHERE extraction = ? AND rule_id = ? GROUP BY 1 ORDER BY 2 DESC", [ext, t["rule_id"]])
        if sig:
            L.append("")
            L.append(f"### Signals on this rule in `{ext}`")
            for s in sig:
                ex = q("""SELECT s.detail, coalesce(o.course_key, s.page_stem) who FROM signals s
                    LEFT JOIN occurrences o ON o.extraction = s.extraction AND o.occurrence_key = s.occurrence_key
                    WHERE s.extraction = ? AND s.rule_id = ? AND s.signal = ? ORDER BY who LIMIT 3""", [ext, t["rule_id"], s["signal"]])
                L.append(f"- `{s['signal']}` × {s['n']} — e.g. " + "; ".join(f"{e['who']}: {e['detail']}" for e in ex))
            L.append(f"- all of them: `golden-datasets signals --rule {t['rule_id']} --extraction {ext}`")
        L.append("")
    L.append("## How to work")
    L.append("")
    names = " ".join(t["rule_id"] for t in targets)
    L.append(f"1. `golden-datasets rule show {names}` — current definition, what/how/why, examples, version history.")
    L.append(f"2. `golden-datasets rule annotations {names} --format jsonl` — every annotation above, with css paths and offsets.")
    L.append("3. `golden-datasets pages get <page_stem> --match <rule_id> --text` — the text of the element a rule matched on that page "
             "(`--css <css_path>` for any element, `--around` for its context). "
             "Read pages this way; this prompt deliberately contains no raw HTML.")
    L.append("4. Write a draft per rule to `drafts/<rule_id>.json`. Change only `definition`, `what`, `how`, `why` and "
             "`examples`. Stay declarative: no code. If the rule format can't express the fix, stop and say so.")
    L.append("5. `golden-datasets rule try drafts/<rule_id>.json` — reruns the draft over the whole crawl and prints a scorecard: "
             "fixed / still wrong / newly wrong (values marked correct that changed), changed rows, and signal counts "
             "before → after. Iterate until every wrong/missing annotation is fixed and nothing marked correct changed.")
    L.append("   Annotations marked QUESTION FOR THE INSTITUTION are waiting on an answer from the college itself: "
             "don't change the rule for them, but mention them in your report.")
    L.append("6. Fill `why` from the annotations: cite the course codes and the expert's notes. Add one example per fix.")
    L.append("7. `golden-datasets rule publish drafts/<rule_id>.json` — writes the new rule version, a new ruleset version and its "
             "extraction (unchanged rules are copied). Do not commit or push anything.")
    L.append("")
    L.append("Report back: what changed and why, the final scorecard, and anything you could not fix.")
    return "\n".join(L) + "\n"


@app.get("/api/c/{catalog}/prompt", response_class=PlainTextResponse)
def prompt(catalog: str, scope: str = "needs-work"):
    return build_prompt(scope)


# ---------------------------------------------------------------------------------------- golden
@app.get("/api/c/{catalog}/golden")
def golden(catalog: str):
    rs = latest_rs()
    ext = extraction_for(rs)
    st = rule_statuses(rs)
    st.pop("_meta")
    n_courses = q("SELECT count(DISTINCT course_key) n FROM occurrences WHERE extraction = ? AND course_key IS NOT NULL", [ext])[0]["n"]
    n_values = q("""SELECT count(*) n FROM matches m JOIN occurrences o USING (extraction, occurrence_key)
        WHERE m.extraction = ? AND m.status = 'found'""", [ext])[0]["n"]
    pubs = []
    for g in cat_info(catalog)["crawls"][0]["golden"]:
        meta = json.loads((ROOT / g["path"] / "publication.json").read_text())
        pubs.append(meta)
    return {"ruleset": rs, "extraction": ext, "rules": list(st.values()), "courses": n_courses, "values": n_values,
            "approved": sum(s["status"] == "approved" for s in st.values()), "total": len(st),
            "pages": q("""SELECT count(DISTINCT o.page_stem) n FROM occurrences o WHERE extraction = ?""", [ext])[0]["n"],
            "target": f"xtra-golden-sets-verified/{catalog}/{studio.CRAWL}/", "publications": pubs}


# ---------------------------------------------------------------------------------------- annotations
@app.post("/api/c/{catalog}/annotations")
async def add_annotation(catalog: str, request: Request):
    body = await request.json()
    rec = {"annotation_id": "ui-" + uuid.uuid4().hex[:12], "type": body.get("type", "verdict"),
           "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "author": body.get("author", "Jared"),
           "catalog": catalog, "crawl": studio.CRAWL, "target": body["target"], "verdict": body.get("verdict"),
           "expected": body.get("expected"), "note": body.get("note"), "supersedes": body.get("supersedes"),
           "imported_from": None}
    with LOCK:
        with UI_LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    return rec


# ---------------------------------------------------------------------------------------- page render
_DROP = ("script", "noscript", "iframe", "object", "embed", "frame", "frameset")


def _scope_css(css: str, root: str) -> str:
    out = []
    for block in css.split("}"):
        if "{" not in block:
            continue
        sel, decl = block.split("{", 1)
        sels = ", ".join(f"{root} {s.strip()}" for s in sel.split(",") if s.strip())
        out.append(f"{sels}{{{decl}}}")
    return "\n".join(out)


@lru_cache(maxsize=48)
def cleaned_page(stem: str) -> str:
    row = q("SELECT url, html_path FROM pages WHERE page_stem = ?", [stem])
    if not row:
        raise HTTPException(404)
    url, path = row[0]["url"], ROOT / row[0]["html_path"]
    doc = lxml.html.fromstring(path.read_bytes())
    for el in list(doc.iter(*_DROP)):
        el.drop_tree()
    for el in doc.xpath("//meta[@http-equiv]"):
        el.drop_tree()
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in list(el.attrib):
            if attr.lower().startswith("on"):
                del el.attrib[attr]
            elif attr in ("href", "src", "action") and el.attrib[attr].strip().lower().startswith("javascript:"):
                el.attrib[attr] = "#"
    head = doc.find("head")
    if head is None:
        head = lxml.html.Element("head")
        doc.insert(0, head)
    base = doc.xpath("//base")
    href = urljoin(url, base[0].get("href")) if base else url
    for b in base:
        b.drop_tree()
    head.insert(0, lxml.html.fragment_fromstring(f'<base href="{href}">'))
    settings = ruleset(latest_rs())["settings"]
    style = lxml.html.Element("style")
    style.set("id", "gds-pane-css")
    style.text = _scope_css(settings.get("pane_css", ""), settings["content_root"]) + (
        "\nhtml{scroll-behavior:auto!important}")
    head.append(style)
    return "<!doctype html>\n" + lxml.html.tostring(doc, encoding="unicode")


@app.get("/api/c/{catalog}/pages/{stem}/render")
def render(catalog: str, stem: str):
    html = cleaned_page(stem)
    csp = ("script-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; "
           "default-src 'self' https: data:; style-src 'self' 'unsafe-inline' https:; img-src 'self' https: data:; font-src 'self' https: data:")
    return HTMLResponse(html, headers={"Content-Security-Policy": csp, "Cache-Control": "max-age=600"})


@app.get("/api/c/{catalog}/pages/{stem}/source")
def page_source(catalog: str, stem: str, css: str | None = None):
    """Pretty HTML of one element (the occurrence) for the HTML view of the page pane."""
    row = q("SELECT url, html_path FROM pages WHERE page_stem = ?", [stem])[0]
    doc = lxml.html.fromstring((ROOT / row["html_path"]).read_bytes())
    el = doc.cssselect(css)[0] if css else doc.cssselect(ruleset(latest_rs())["settings"]["content_root"])[0]
    for s in el.iter("svg"):
        for c in list(s):
            s.remove(c)
    from lxml import etree
    text = etree.tostring(el, pretty_print=True, encoding="unicode", method="html")
    return {"css_path": css, "html": text[:60000]}


# ---------------------------------------------------------------------------------------- static
@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    setup()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
