"""`golden-datasets import-v2`: review-ui-v2's rules and Jared's verdicts, imported (spec §3.2, §5.5).

1. v2's `rules.json` (the copy saved with the extraction the latest review session used) → rule versions v1 and
   ruleset v1. Label rules become page rules (renamed: §2 bans "label"); the `scope / repeat / repeat_filter`
   shared by the field rules of one label becomes a record locator (D2); only the eight in-scope properties are
   kept (§4.4).
2. `extract` rs-0001, if it doesn't exist yet: annotations point at its occurrences and matches.
3. The session's decisions, notes and flags → `annotations.jsonl` events, with the tally printed.

Reading v2's files never changes them. Annotation ids are derived from the v2 decisions, so a second import adds
nothing.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict

from . import engine, layout, model, rulesets
from .catalogs import info
from .context import Ctx
from .errors import UserError
from .log import AnnotationLog
from .storage import open_root

IN_SCOPE = {label for label, _ in model.PROPERTIES}
PAGE_RULE_IDS = {
    "label-course-page": "course-page",
    "label-program-page": "program-page",
    "label-course-on-program-page": "program-page-with-courses",
}
LOCATOR_FOR = {"label-course-page": "locator-course-page", "label-course-on-program-page": "locator-program-requirement"}
LOCATOR_KEYS = ("scope", "repeat", "repeat_filter")

# Prose written for AVC by the prototype (reviewed with Eric). Other catalogs get prose generated from the
# definitions (see `describe`), to be rewritten by Claude as rules change.
AVC_PROSE = {
    "course-page": (
        "Pages at /catalog/2026-27/course/<code> that open with the orange course header: the code ('GEOG 222:'), "
        "the title and the units.",
        "The URL path is /catalog/<year>/course/<code> and the main content has a course header "
        "(an h3 inside header.header, which holds the course code)."),
    "program-page": (
        "Pages at /catalog/2026-27/program/<name> for one degree or certificate, with a collapsible 'Program "
        "Requirements' section.",
        "The URL path is /catalog/<year>/program/<slug> and the main content contains the "
        "requirements builder (#accordion-program-builder-rules)."),
    "program-page-with-courses": (
        "Program pages whose 'Program Requirements' section lists at least one course line, such as "
        "'MATH150 - Calculus and Analytic Geometry   5'.",
        "Same URL test as program-page, and the requirements builder has at least one requirement "
        "line (.new-rule)."),
    "locator-course-page": (
        "On a course page, everything below the site's top bar (header, intro paragraphs, Units and Hours) "
        "is one course.",
        "One occurrence per course page: the content root (#mainContent) itself. No repetition."),
    "locator-program-requirement": (
        "On a program page, each line in 'Program Requirements' that starts with a course code and ' - ' "
        "('CS150 - Discrete Structures   4'). Heading lines like 'Complete all of the following' are skipped.",
        "Each .new-rule inside #accordion-program-builder-rules is a candidate. Keep it only when its "
        ".rule-name text starts with a course code followed by ' - ' (for example 'AJ101 - Introduction to "
        "Administration of Justice'); lines such as 'Complete 6 units from…' are skipped."),
    "course-code": (
        "The small code line above the course title in the orange header, e.g. 'GEOG 222:', without the colon.",
        "Text of the h3 in the course header ('GEOG 222:'), trimmed, with the trailing colon removed."),
    "course-external-id": (
        "The same code line above the course title, written without spaces: 'GEOG 222:' gives 'GEOG222'.",
        "Same element as Coded Notation (header.header h3); trailing colon removed, then every space removed."),
    "course-name": (
        "The large title in the orange course header, e.g. 'Cartography for Geographic Information Science (GIS)'.",
        "Text of the h2 in the course header, trimmed."),
    "course-description": (
        "The intro paragraph(s) under the orange course header on a course page, exactly as shown, including any "
        "leading 'Prerequisite:' or 'Advisory:' line.",
        "The whole text of the intro block (.introtext), trimmed and otherwise verbatim."),
    "course-subject-webpage": (
        "Nothing on the page itself: the address of the course page, e.g. .../catalog/2026-27/course/geog222.",
        "The URL of the course page itself; nothing is read from the page."),
    "course-learning-type": (
        "Nothing on the page itself: every course page gives the fixed value 'Course'.", "Constant 'Course'."),
    "course-lifecycle": (
        "Nothing on the page itself: every course in this year's catalog gives the fixed value 'Active'.",
        "Constant 'Active'."),
    "course-language": (
        "Nothing on the page itself: the catalog never states a language, so every course gives 'English'.",
        "Constant 'English'."),
    "stub-code": (
        "On a program page's requirement line, the code before ' - ': 'MATH150' in 'MATH150 - Calculus and "
        "Analytic Geometry'.",
        "In the requirement line's .rule-name, the code before ' - ' (letters, an optional letter, digits, "
        "optional letters), trimmed."),
    "stub-external-id": (
        "The same code at the start of a program requirement line, written without spaces.",
        "Same text as the stub's Coded Notation, with every space removed."),
    "stub-name": (
        "On a program page's requirement line, the title after ' - ': 'Calculus and Analytic Geometry'.",
        "In the requirement line's .rule-name, the text after ' - ', trimmed."),
    "stub-learning-type": (
        "Nothing on the page itself: every course line on a program page gives the fixed value 'Course'.",
        "Constant 'Course'."),
}
# AVC's reviewed reveal sheet (spec feedback 12): opens the program requirement accordions, scoped to content.
AVC_PANE_CSS = (".accordionheader{height:auto!important;overflow:visible!important}"
                ".accordionheader-x-nested{display:block!important;opacity:1!important;transform:none!important;"
                "max-height:none!important;pointer-events:auto!important}")
LABEL_TEXT = (r"^\s*(Prerequisites?|Corequisites?|Advisory|Recommended Preparation|Units?|Description|Course)\s*:"
              r"|\b(Prerequisites?|Corequisites?)\s*:")


def iso(v2ts: str) -> str:
    """'2026-10-21T20-19-46Z' → '2026-10-21T20:19:46Z'."""
    if "T" not in v2ts or ":" in v2ts:
        return v2ts
    d, t = v2ts.split("T")
    return f"{d}T{t[:-1].replace('-', ':')}Z"


def _sel(s: str) -> str:
    return f"`{s}`"


def describe(rule: dict, page_rule_names: dict[str, str]) -> tuple[str, str]:
    """Plain-words what / how for a rule imported without hand-written prose."""
    d, kind = rule["definition"], rule["kind"]
    if kind == "page":
        what = {"course-page": "Pages that describe courses.", "program-page": "Pages that describe one program.",
                "program-page-with-courses": "Program pages whose requirements list courses."}.get(
            rule["rule_id"], f"Pages labelled {d.get('label')}.")
        parts = []
        if d.get("url_regex"):
            parts.append(f"the address matches {_sel(d['url_regex'])}")
        if d.get("requires_selector"):
            parts.append(f"the page has {_sel(d['requires_selector'])}")
        if d.get("forbids_selector"):
            parts.append(f"the page has no {_sel(d['forbids_selector'])}")
        return what, "A page matches when " + " and ".join(parts or ["always"]) + "."
    if kind == "locator":
        pages = " or ".join(page_rule_names.get(p, p) for p in d.get("page_rules", []))
        if d.get("repeat"):
            what = f"On {pages.lower()}, each {_sel(d['repeat'])} block is one course."
            how = f"Every {_sel(d['repeat'])} inside the content root" + (
                f" (within {_sel(d['scope'])})" if d.get("scope") else "") + " is one occurrence"
            if d.get("repeat_filter"):
                f = d["repeat_filter"]
                how += f", kept only when the text of {_sel(f.get('selector') or 'the block')} matches {_sel(f['regex'])}"
            return what, how + "."
        return (f"On {pages.lower()}, the whole page content is one course.",
                "One occurrence per page: the content root itself. No repetition.")
    rtype = d["rule_type"]
    if rtype == "constant":
        return (f"Nothing on the page itself: every course gives the fixed value '{d['value']}'.",
                f"Constant '{d['value']}'.")
    if rtype == "source_url":
        return ("Nothing on the page itself: the address of the page the course is on.",
                "The URL of the page itself; nothing is read from the page.")
    src = f"the text of {_sel(d['selector'])} in the course block" if d.get("selector") else "the course block's whole text"
    how = src[0].upper() + src[1:]
    if d.get("regex"):
        how += f", matched against {_sel(d['regex'])} (group {d.get('group', 1)})"
    if d.get("transforms"):
        how += f", then {', '.join(d['transforms'])}"
    if d.get("map"):
        how += ", then mapped through a lookup table"
    what = rule.get("_v2_description") or f"The course's {rule['property_label']}."
    return what, how + "."


def build_v1_rules(ctx: Ctx, v2: dict) -> tuple[dict[str, dict], dict, dict]:
    """v2 ruleset → (drafts for rule versions v1, settings, stats)."""
    avc = ctx.catalog == "avc-elumenapp-com-catalog-2026-27-welcome"
    drafts: dict[str, dict] = {}
    names = {}
    for lr in v2["label_rules"]:
        rid = PAGE_RULE_IDS.get(lr["rule_id"], lr["rule_id"].removeprefix("label-"))
        definition = {k: lr[k] for k in ("url_regex", "requires_selector", "forbids_selector") if k in lr}
        definition["label"] = lr["label"]
        drafts[rid] = {"rule_id": rid, "kind": "page", "ctdl_property": None, "property_label": None,
                       "definition": definition, "why": "", "examples": [],
                       "imported_from": {"v2_rule_id": lr["rule_id"], "v2_description": lr.get("description")}}
        names[rid] = {"course-page": "Course pages", "program-page": "Program pages",
                      "program-page-with-courses": "Program pages that list courses"}.get(rid, rid)
    in_scope = [fr for fr in v2["field_rules"] if fr["canonical_label"] in IN_SCOPE]
    by_label = defaultdict(list)
    for fr in in_scope:
        if len(fr["applies_to"]) != 1:
            raise UserError(f"{fr['rule_id']}: applies to {fr['applies_to']}; expected one label rule")
        by_label[fr["applies_to"][0]].append(fr)
    locator_of = {}
    for label_rule, frs in sorted(by_label.items()):
        loc_id = LOCATOR_FOR.get(label_rule, f"locator-{label_rule.removeprefix('label-')}")
        shared = {k: frs[0]["properties"].get(k) for k in LOCATOR_KEYS}
        for fr in frs:  # the claim (research B10) is checked, not trusted
            got = {k: fr["properties"].get(k) for k in LOCATOR_KEYS}
            if got != shared:
                raise UserError(f"{fr['rule_id']}: scope/repeat/repeat_filter differs from {frs[0]['rule_id']}; "
                                "can't pull out one record locator")
        if shared["scope"] == "#xtra-root":
            shared["scope"] = None
        page_rule = PAGE_RULE_IDS.get(label_rule, label_rule)
        drafts[loc_id] = {"rule_id": loc_id, "kind": "locator", "ctdl_property": None, "property_label": None,
                          "definition": {"page_rules": [page_rule], **shared}, "why": "", "examples": [],
                          "imported_from": {"v2_field_rules": sorted(f["rule_id"] for f in frs),
                                            "v2_key": "properties.repeat"}}
        for fr in frs:
            locator_of[fr["rule_id"]] = loc_id
    for fr in in_scope:
        props = {k: v for k, v in fr["properties"].items() if k not in LOCATOR_KEYS}
        examples = [{"input": fr["example_input"], "output": fr["example_output"]}] if "example_input" in fr else []
        drafts[fr["rule_id"]] = {
            "rule_id": fr["rule_id"], "kind": "field", "ctdl_property": fr.get("ctdl_property"),
            "property_label": fr["canonical_label"],
            "definition": {"locator": locator_of[fr["rule_id"]], "rule_type": fr["rule_type"], **props},
            "why": "", "examples": examples, "_v2_description": fr.get("description"),
            "imported_from": {"v2_rule_id": fr["rule_id"], "v2_description": fr.get("description")}}
    for rid, dr in drafts.items():
        if avc and rid in AVC_PROSE:
            dr["what"], dr["how"] = AVC_PROSE[rid]
        else:
            dr["what"], dr["how"] = describe(dr, names)
        dr.pop("_v2_description", None)
        dr["depends_on"] = model.dependencies(dr)
    code_rules = {}
    for loc_id in {d["definition"]["locator"] for d in drafts.values() if d["kind"] == "field"}:
        code_rules[loc_id] = next(rid for rid, d in sorted(drafts.items()) if d["kind"] == "field"
                                  and d["definition"]["locator"] == loc_id and d["property_label"] == "Coded Notation")
    meta = info(ctx.catalog)
    settings = {
        "content_root": v2["content_root"], "page_title": v2.get("page_title", []),
        "pane_css": AVC_PANE_CSS if avc else "",
        "pane_css_v2": v2.get("pane_css"),
        "course_key_rule": dict(sorted(code_rules.items())),
        "signals": {"course_code_pattern": meta.get("course_code_pattern") or r"\b[A-Z]{2,5} ?\d{3}[A-Z]?\b",
                    "label_text_pattern": LABEL_TEXT, "shape_outlier_max_share": 0.02, "shape_dominance": 0.5,
                    "length_outlier_percentiles": [1, 99], "missed_page_min_codes": 5, "page_allow": []},
    }
    stats = {"rules": len(drafts), "by_kind": dict(Counter(d["kind"] for d in drafts.values())),
             "skipped_out_of_scope_rules": len(v2["field_rules"]) - len(in_scope)}
    return drafts, settings, stats


# =====================================================================================================
# Sessions
# =====================================================================================================
def find_session(v2root, catalog: str, crawl: str, session: str | None) -> tuple[str, dict]:
    base = f"{catalog}/{crawl}/review-ui"
    sessions = [session] if session else sorted(v2root.list_dirs(base), reverse=True)
    for s in sessions:
        if v2root.exists(f"{base}/{s}/decisions.json"):
            return s, v2root.read_json(f"{base}/{s}/session.json")
    raise UserError(f"no v2 review session with decisions under {v2root.uri}/{base}")


def _opt_json(root, path: str, default):
    try:
        data = root.read_json(path)
    except FileNotFoundError:
        return default
    return data if data else default


def locate_expected(doc, css: str, expected: str) -> dict:
    """Find the expected text inside the element at `css` (document root); offsets in its textContent."""
    out = {"text": expected, "css_path": None, "char_start": None, "char_end": None, "quote": None,
           "located_by": "not found on page"}
    el = engine.select_one(doc, css, True) if css else None
    if el is None:
        return out
    text, brs = engine.text_of(el)
    pattern = r"\s+".join(re.escape(w) for w in expected.split())
    m = re.search(pattern, text) if pattern else None
    if not m:
        return out
    a, b = m.span()
    tc = engine.text_content(el)
    a2, b2 = engine.to_text_content(a, brs), engine.to_text_content(b, brs)
    out.update(css_path=css, char_start=a2, char_end=b2, located_by="golden-datasets import-v2 text search",
               quote={"prefix": tc[max(0, a2 - 30):a2],
                      "exact": tc[a2:b2] if b2 - a2 <= 120 else tc[a2:a2 + 60] + "…" + tc[b2 - 60:b2],
                      "suffix": tc[b2:b2 + 30]})
    return out


def import_annotations(ctx: Ctx, v2root, session: str, ext: str) -> tuple[list[dict], Counter]:
    sess = f"{ctx.catalog}/{ctx.crawl}/review-ui/{session}"
    decisions = v2root.read_json(f"{sess}/decisions.json")
    notes = _opt_json(v2root, f"{sess}/notes.json", [])
    flags = _opt_json(v2root, f"{sess}/flags.json", {})
    pages = {p["url"]: p["page_stem"] for p in ctx.pages()}
    pages.update({p["requested_url"]: p["page_stem"] for p in ctx.pages()})
    occs = ctx.table(ext, "occurrences").to_pylist()
    matches = ctx.table(ext, "matches").to_pylist()
    ck_of = {o["occurrence_key"]: o["course_key"] for o in occs}
    occ_path = {o["occurrence_key"]: o["css_path"] for o in occs}
    m_by = {}
    for m in matches:
        m_by.setdefault((m["rule_id"], m["page_stem"], ck_of[m["occurrence_key"]]), m)
    o_by = {}
    for o in occs:
        o_by.setdefault((o["page_stem"], o["course_key"]), o)
    rs_version = ctx.extraction_meta(ext)["ruleset_version"]
    _, rules = ctx.ruleset_rules(rs_version)
    rule_for = {(r["property_label"], r["definition"]["locator"]): rid for rid, r in rules.items() if r["kind"] == "field"}
    notes_by = defaultdict(list)
    for n in notes:
        notes_by[n["target"]].append(n)
    docs: dict = {}

    def page_doc(stem):
        if stem not in docs:
            docs[stem] = engine.parse(ctx.page_path(stem).read_bytes())
        return docs[stem]

    stats: Counter = Counter()
    out: list[dict] = []

    def aid(imported: dict, prefix="an") -> str:
        return f"{prefix}-" + hashlib.sha1(model.canon(imported).encode()).hexdigest()[:12]

    def target(kind, rule_id, stem, occ, value_seen=None, vi=None):
        return {"kind": kind, "rule_id": rule_id,
                "rule_version_seen": rules[rule_id]["version"] if rule_id else None,
                "extraction_seen": ext, "occurrence_key": occ["occurrence_key"] if occ else None,
                "course_key": occ["course_key"] if occ else None, "page_stem": stem, "value_index": vi,
                "value_seen": value_seen}

    def event(at, author, tgt, verdict, imported, expected=None, note=None):
        return {"annotation_id": aid(imported), "type": "verdict", "at": iso(at), "author": author,
                "catalog": ctx.catalog, "crawl": ctx.crawl, "target": tgt, "verdict": verdict,
                "expected": expected, "note": note or None, "supersedes": None, "imported_from": imported}

    groups = defaultdict(list)
    for key, d in decisions.items():
        if d["kind"] == "field":
            groups[(d["record_id"], d["canonical_label"], d["source_url"])].append((key, d))
    for (rec, label, url), items in sorted(groups.items()):
        if label not in IN_SCOPE:
            stats["skipped_out_of_scope_field"] += len(items)
            continue
        stem = pages.get(url)
        occ = o_by.get((stem, rec)) if stem else None
        rule_id = rule_for.get((label, occ["locator_rule_id"])) if occ else None
        match = m_by.get((rule_id, stem, rec)) if rule_id else None
        if match is None:
            stats["skipped_no_matching_occurrence"] += len(items)
            continue
        by_status = defaultdict(list)
        for key, d in items:
            by_status[d["status"]].append((key, d))
        for key, d in by_status.get("accepted", []):
            if model.canon(_n(d.get("value"))) != model.canon(_n(match["value"])):
                stats["accepted_value_differs_from_rs-0001"] += 1
            imported = {"source": "review-ui-v2", "session": session, "decisions": [
                {"key": key, "status": "accepted", "author": d["author"], "seq": int(d["seq"]),
                 "carried_from": d.get("carried_from")}],
                "notes": [n["id"] for n in notes_by.get(key, [])]}
            note = " ".join(n["text"] for n in notes_by.get(key, []))
            out.append(event(d["at"], d["author"], target("match", rule_id, stem, occ, d.get("value"), 0), "correct",
                             imported, note=note))
            stats["correct"] += 1
        rejected, missing = by_status.get("rejected", []), by_status.get("missing", [])
        full_css = model.full_css_path(occ_path[match["occurrence_key"]], match["css_path"]) or occ["css_path"]
        if rejected:
            (rkey, r) = rejected[0]
            decs = [{"key": rkey, "status": "rejected", "author": r["author"], "seq": int(r["seq"])}]
            expected = None
            if missing:  # reject + missing pair → one `wrong` with the expected text (spec §12.1 author rule)
                mkey, md = missing[0]
                decs.append({"key": mkey, "status": "missing", "author": md["author"], "seq": int(md["seq"])})
                expected = {**locate_expected(page_doc(stem), full_css, md["expected_value"]), "author": md["author"]}
                missing = missing[1:]
            nts = notes_by.get(rkey, [])
            imported = {"source": "review-ui-v2", "session": session, "decisions": decs, "notes": [n["id"] for n in nts]}
            out.append(event(r["at"], r["author"], target("match", rule_id, stem, occ, r.get("value"), 0), "wrong",
                             imported, expected, " ".join(n["text"] for n in nts)))
            stats["wrong (reject + missing joined)" if expected else "wrong"] += 1
        for mkey, md in missing:
            # A field rule row can't be "missing" (spec §4.3): the value is wrong, and this is the right text.
            imported = {"source": "review-ui-v2", "session": session,
                        "decisions": [{"key": mkey, "status": "missing", "author": md["author"], "seq": int(md["seq"])}]}
            expected = {**locate_expected(page_doc(stem), full_css, md["expected_value"]), "author": md["author"]}
            out.append(event(md["at"], md["author"], target("match", rule_id, stem, occ, match["value"], 0), "wrong",
                             imported, expected))
            stats["wrong (v2 missing on a field)"] += 1
    for key, d in sorted(decisions.items()):
        if d["kind"] != "label":
            continue
        rid = PAGE_RULE_IDS.get(d.get("rule_id") or "")
        stem = pages.get(d["source_url"])
        if rid not in rules or stem is None or d["status"] not in ("accepted", "rejected"):
            stats["skipped_label_without_page_rule"] += 1  # 'missing' Credential/Competency labels
            continue
        verdict = {"accepted": "correct", "rejected": "wrong"}[d["status"]]
        imported = {"source": "review-ui-v2", "session": session, "decisions": [
            {"key": key, "status": d["status"], "author": d["author"], "seq": int(d["seq"]), "reasons": d.get("reasons")}]}
        out.append(event(d["at"], d["author"], target("page", rid, stem, None, d.get("value")), verdict, imported))
        stats[f"page rule {verdict}"] += 1
    for tkey, f in sorted(flags.items()):
        if f.get("scope") != "page" or not f.get("flagged", True):
            stats["skipped_flag"] += 1
            continue
        imported = {"source": "review-ui-v2", "session": session, "flag": tkey, "seq": int(f.get("seq") or 0)}
        out.append(event(f["at"], f["author"], target("page", None, f["stem"], None), "question", imported,
                         note=f.get("note")))
        stats["question (page flag)"] += 1
    used = {nid for a in out for nid in (a["imported_from"].get("notes") or [])}
    stats["skipped_note_out_of_scope"] = sum(1 for n in notes if n.get("id") not in used)
    for rid, r in sorted(rules.items()):  # constant and URL rules start approved (spec §4.3)
        if r["kind"] == "field" and r["definition"]["rule_type"] in model.DERIVED_RULE_TYPES:
            imported = {"source": "golden-datasets import-v2", "rule": rid, "version": r["version"]}
            out.append({"annotation_id": aid(imported, "ap"), "type": "approve", "at": rulesets.now_iso(),
                        "author": "golden-datasets import-v2", "catalog": ctx.catalog, "crawl": None,
                        "target": {"kind": "rule", "rule_id": rid, "rule_version_seen": r["version"],
                                   "extraction_seen": None, "occurrence_key": None, "course_key": None,
                                   "page_stem": None, "value_index": None, "value_seen": None},
                        "verdict": None, "expected": None,
                        "note": "Constant / page-URL rule: approved on import (spec §4.3).", "supersedes": None,
                        "imported_from": imported})
            stats["approve (constant/URL rule)"] += 1
    out.sort(key=lambda a: (a["at"], a["annotation_id"]))
    return out, stats


def _n(v):
    return re.sub(r"\s+", " ", v or "").strip().lower()


def import_v2(ctx: Ctx, v2_root: str | None, session: str | None, log=print) -> dict:
    from .extract import extract

    v2root = open_root(v2_root) if v2_root else ctx.root
    session, sess_meta = find_session(v2root, ctx.catalog, ctx.crawl, session)
    v2_ext = sess_meta["extraction_id"]
    rules_path = f"{ctx.catalog}/{ctx.crawl}/extractions/{v2_ext}/rules.json"
    v2 = v2root.read_json(rules_path)
    result = {"session": session, "v2_rules_json": rules_path}

    if not ctx.ruleset_versions():
        drafts, settings, stats = build_v1_rules(ctx, v2)
        rules = rulesets.plan_versions(ctx, drafts, {})
        rulesets.publish(ctx, rules, settings, f"Imported from review-ui-v2 rules.json (copy in extraction {v2_ext}).",
                         "golden-datasets import-v2",
                         {"imported_from": {"v2_ruleset_id": v2.get("ruleset_id"), "v2_version": v2.get("version"),
                                            "v2_rules_json": rules_path}})
        result.update(stats)
    else:
        result["rules"] = "already imported"
    ext = ctx.extraction_for(1)
    if ext is None:
        log("  extracting rs-0001 …")
        ext = extract(ctx, 1, created_by="golden-datasets import-v2")["extraction"]
    alog = AnnotationLog(ctx.root, layout.annotations(ctx.catalog))
    have = {e["annotation_id"] for e in alog.events()}
    events, stats = import_annotations(ctx, v2root, session, ext)
    new = [e for e in events if e["annotation_id"] not in have]
    alog.append_many(new)
    result.update({"annotations": len(events), "appended": len(new), **dict(stats)})
    return result


def cmd_import_v2(args) -> int:
    ctx = Ctx.from_args(args)
    out = import_v2(ctx, args.v2_root, args.session)
    for k, v in out.items():
        print(f"  {k}: {v}")
    return 0
