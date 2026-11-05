"""The property list (property-rules spec §4.1): one property rule per CLI Extraction Label (column F) of the Phase 1
Extraction tab of "xTRA: Learning Opportunity BU Template", plus Learning Type.

The list lives in the checked-in `properties.csv` beside this module. The app never reads the sheet at run time:
- `golden-datasets properties sync` writes the file from the sheet (the diff is reviewed like code);
- `golden-datasets properties list` prints it;
- `golden-datasets properties apply` adds the file's new properties to each catalog, with no rule yet (§4.6).

Paths are stored as the sheet writes them (`ceterms:creditValue>schema:minValue`) and shown to people with arrows.
"""

from __future__ import annotations

import csv
import io
import re
import sys
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

from .errors import UserError

FILE = Path(__file__).with_name("properties.csv")
SHEET_XLSX = ("https://docs.google.com/spreadsheets/d/1zFG1Qzn4NTrvb5KTxucKnz-gPd8H_W0oYYRdh7jT8ro/export"
              "?format=xlsx")
PHASE1_TAB, COURSE_TAB = "Phase 1 Extraction", "Course"
COLUMNS = ["rule_id", "path", "sheet_path", "path_note", "label", "parent", "profile", "multiple", "required",
           "course_key", "sheet_row", "status", "vocabulary", "definition_text", "sample"]
BOOLS = ("multiple", "required", "course_key")

#: Learning Type isn't on the Phase 1 tab: a constant `Course` rule with no path (§4.1).
LEARNING_TYPE = {"rule_id": "course-learning-type", "path": "", "sheet_path": "", "path_note": "",
                 "label": "Learning Type", "parent": "", "profile": "", "multiple": False, "required": True,
                 "course_key": False, "sheet_row": 0, "status": "Include", "vocabulary": "", "sample": "Course",
                 "definition_text": "The type of learning opportunity. Always Course here (the Studio's own column)."}
#: Today's eight keep their rule ids (§4.1).
KEPT_IDS = {"ceterms:codedNotation": "course-code", "ceterms:identifier": "course-external-id",
            "ceterms:name": "course-name", "ceterms:description": "course-description",
            "ceterms:subjectWebpage": "course-subject-webpage", "ceterms:lifeCycleStatusType": "course-lifecycle",
            "ceterms:inLanguage": "course-language"}
#: The Required block of decision #5, used when the Course tab can't be read (a CSV export of one tab).
REQUIRED_FALLBACK = ("ceterms:identifier", "ceterms:name", "ceterms:description", "ceterms:subjectWebpage",
                     "ceterms:lifeCycleStatusType", "ceterms:inLanguage")
#: The Rules tab's fixed order for required properties (§4.8): the course key first.
REQUIRED_ORDER = ("ceterms:codedNotation", "ceterms:identifier", "", "ceterms:name", "ceterms:description",
                  "ceterms:subjectWebpage", "ceterms:lifeCycleStatusType", "ceterms:inLanguage")
#: Names the sheet's column D doesn't give yet (phase1-followups spec §2.1): drop an entry once column D says it.
LABELS = {"ceterms:creditValue>schema:value": "Credit Unit Value"}
#: Rows the sheet writes in a way sync doesn't take as written (§4.1).
SKIP_PATHS = {"ceterms:learningOpportunityType": "removed from the sheet (W3): not a CTDL property",
              # Estimated Duration is one list-of-objects rule (sme-fixes §5.1): its children are fields, not rules
              **{f"ceterms:estimatedDuration>{c}": "a field of the Estimated Duration list (profiles_rule.py)"
                 for c in ("ceterms:description", "ceterms:exactDuration", "ceterms:minimumDuration",
                           "ceterms:maximumDuration", "ceterms:timeRequired")}}


# --- reading -------------------------------------------------------------------------------------------
def _bool(v) -> bool:
    return v is True or str(v).strip().lower() == "true"


@lru_cache(maxsize=1)
def _load(path: str, mtime: float) -> tuple[dict, ...]:
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        r = {k: r.get(k, "") for k in COLUMNS}
        for k in BOOLS:
            r[k] = _bool(r[k])
        r["sheet_row"] = int(r["sheet_row"] or 0)
        out.append(r)
    return tuple(out)


def load(path: Path | None = None) -> list[dict]:
    """Every row of the file, in sheet order (Learning Type, with no sheet row, first)."""
    p = path or FILE
    if not p.exists():
        return []
    return [dict(r) for r in _load(str(p), p.stat().st_mtime)]


def active(path: Path | None = None) -> list[dict]:
    """The rows still on the sheet (not `removed`)."""
    return [r for r in load(path) if r["status"] != "removed"]


def write(rows: list[dict], path: Path | None = None) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("true" if r[k] else "false") if k in BOOLS else r.get(k, "") for k in COLUMNS})
    (path or FILE).write_text(buf.getvalue())


def shown(path: str | None) -> str:
    """A path for people: `ceterms:creditValue → schema:minValue` (R8)."""
    return (path or "").replace(">", " → ")


def leaf(path: str | None) -> str:
    return (path or "").rsplit(">", 1)[-1]


def label_of(path: str) -> str:
    """A term in words, for a flat row with no name: `ceterms:hasPart` → `Has Part`."""
    term = leaf(path).split(":", 1)[-1]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", term)[:1].upper() + re.sub(r"(?<=[a-z])(?=[A-Z])", " ", term)[1:]


def rule_id_for(path: str) -> str:
    """A new property's rule id, from its path: `ceterms:creditValue>schema:minValue` → `course-credit-value-min-value`."""
    if path in KEPT_IDS:
        return KEPT_IDS[path]
    parts = [re.sub(r"(?<=[a-z])(?=[A-Z])", "-", p.split(":", 1)[-1]).lower() for p in path.split(">")]
    return "course-" + "-".join(parts)


# --- the sheet -----------------------------------------------------------------------------------------
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(data: bytes) -> dict[str, list[list[str]]]:
    """Every tab of an xlsx file as rows of text (no library: the sheet only needs cell text)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for sheet in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", _NS):
        target = rels[sheet.get(_REL)].lstrip("/")
        target = target if target.startswith("xl/") else f"xl/{target}"
        rows: list[list[str]] = []
        for row in ET.fromstring(z.read(target)).iter(f"{{{_NS['m']}}}row"):
            n = int(row.get("r")) - 1
            while len(rows) < n:
                rows.append([])
            cells: list[str] = []
            for c in row.findall("m:c", _NS):
                i = _col(c.get("r"))
                v = c.find("m:v", _NS)
                if c.get("t") == "s" and v is not None:
                    text = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
                else:
                    text = v.text if v is not None and v.text else ""
                cells += [""] * (i - len(cells)) + [text]
            rows.append(cells)
        out[sheet.get("name")] = rows
    return out


def required_from_course_tab(rows: list[list[str]]) -> set[str] | None:
    """The CTDL terms of the Course tab's Required Properties block (P2): the rows after the "Required Properties"
    header, up to the next section header (a row with one cell). None when there is no such block."""
    start = next((i for i, r in enumerate(rows) if r and r[0].strip().lower() == "required properties"), None)
    if start is None:
        return None
    found: set[str] = set()
    for r in rows[start + 1:]:
        cells = [c.strip() for c in r if c and c.strip()]
        if len(cells) <= 1:
            break
        if len(r) > 1 and re.fullmatch(r"ceterms:[A-Za-z]+", r[1].strip()):
            found.add(r[1].strip())
    return found or None


def sheet_rows(source: str | None) -> tuple[list[list[str]], set[str] | None]:
    """(Phase 1 rows, required terms or None) from an xlsx file, a CSV of the Phase 1 tab, or the sheet itself."""
    if source and source.lower().endswith(".csv"):
        with open(source, newline="") as fh:
            return list(csv.reader(fh)), None
    if source:
        data = Path(source).read_bytes()
    else:
        with urllib.request.urlopen(SHEET_XLSX, timeout=60) as resp:
            data = resp.read()
    tabs = read_xlsx(data)
    if PHASE1_TAB not in tabs:
        raise UserError(f"the workbook has no {PHASE1_TAB!r} tab (tabs: {', '.join(tabs)})")
    return tabs[PHASE1_TAB], required_from_course_tab(tabs.get(COURSE_TAB, []))


def from_sheet(rows: list[list[str]], required: set[str] | None) -> tuple[list[dict], list[str]]:
    """The file's rows from the Phase 1 tab (row 1 is the header), and warnings. Columns: A status, C profile,
    D label, E shorthand, F CLI Extraction Label, G definition, J vocabulary, K Single / Multiple, L sample."""
    warnings: list[str] = []
    req = set(required) if required else set(REQUIRED_FALLBACK)
    if required is None:
        warnings.append("Course tab not read: required properties are decision #5's list")
    got: list[dict] = []
    multiple_of: dict[str, bool] = {}
    for n, r in enumerate(rows[1:], start=2):
        def cell(i: int, r: list[str] = r) -> str:
            return r[i].strip() if i < len(r) and r[i] else ""
        f = cell(5)
        if not f:
            continue
        if f in SKIP_PATHS:
            warnings.append(f"row {n}: {f} skipped: {SKIP_PATHS[f]}")
            continue
        status = cell(0)
        if not status:
            warnings.append(f"row {n}: blank status")
        got.append({"sheet_row": n, "sheet_path": f, "path": f, "path_note": "", "profile": cell(2),
                    "column_d": cell(3), "status": status, "definition_text": cell(6), "vocabulary": cell(9),
                    "single_multiple": cell(10), "sample": cell(11)})
    # A child path sits under the nearest parent row above it (P15): a path whose parent isn't that row is corrected.
    parent_row = None
    for g in got:
        if ">" not in g["path"]:
            parent_row = g
            continue
        head, rest = g["path"].split(">", 1)
        if parent_row is not None and head != parent_row["path"] and parent_row["profile"] == "" \
                and g["profile"] and any(x["path"] == g["path"] for x in got if x is not g):
            fixed = f"{parent_row['path']}>{rest}"
            g["path"] = fixed
            g["path_note"] = (f"Row {g['sheet_row']} repeats {head}>{rest}; its parent is row {parent_row['sheet_row']}")
            warnings.append(f"row {g['sheet_row']}: {g['sheet_path']} repeats an earlier row; read as {fixed} (P15)")
    paths = [g["path"] for g in got]
    for p in sorted({p for p in paths if paths.count(p) > 1}):
        raise UserError(f"the sheet has {p} twice")
    by_path = {g["path"]: g for g in got}
    # Single / Multiple: blank rows copy the Prerequisite group's shape (P4); a child of a list is a list (P14).
    for g in got:
        sm = g["single_multiple"].lower()
        if sm in ("single", "multiple"):
            multiple_of[g["path"]] = sm == "multiple"
            continue
        leaf_term = leaf(g["path"])
        if ">" not in g["path"]:
            multiple_of[g["path"]] = True
        else:
            multiple_of[g["path"]] = leaf_term != "ceterms:description"
        warnings.append(f"row {g['sheet_row']}: no Single / Multiple; read as "
                        f"{'Multiple' if multiple_of[g['path']] else 'Single'} like the Prerequisite group (P4)")
    for g in got:
        if ">" in g["path"]:
            head = g["path"].split(">", 1)[0]
            if multiple_of.get(head) and not multiple_of[g["path"]] and head == "ceterms:estimatedDuration":
                multiple_of[g["path"]] = True
                warnings.append(f"row {g['sheet_row']}: {g['path']} says Single, but its parent is a list: a list "
                                "too (P14)")
    out = [dict(LEARNING_TYPE)]
    for g in got:
        path = g["path"]
        parent = path.split(">", 1)[0] if ">" in path else ""
        if path in LABELS:
            label = LABELS[path]
        elif g["column_d"] and not (parent and g["column_d"] in {x["column_d"] for x in got if x is not g}):
            label = g["column_d"]
        elif parent:
            label = f"{by_path[parent]['column_d'] or label_of(parent)}: {g['column_d'] or label_of(path)}"
        else:
            label = label_of(path)
        out.append({"rule_id": rule_id_for(path), "path": path, "sheet_path": g["sheet_path"],
                    "path_note": g["path_note"], "label": label, "parent": parent, "profile": g["profile"],
                    "multiple": multiple_of[path], "required": path in req or path == "ceterms:codedNotation",
                    "course_key": path == "ceterms:codedNotation", "sheet_row": g["sheet_row"],
                    "status": g["status"], "vocabulary": g["vocabulary"], "definition_text": g["definition_text"],
                    "sample": g["sample"]})
    labels = [r["label"] for r in out]
    for lb in sorted({x for x in labels if labels.count(x) > 1}):
        raise UserError(f"two properties would be named {lb!r}")
    return out, warnings


def merge(old: list[dict], new: list[dict], accept_renames: bool) -> tuple[list[dict], dict, list[str]]:
    """The file after a sync: rule ids kept, rows gone from the sheet kept as `removed`, never deleted.
    A changed path or name on an existing rule id needs `accept_renames`."""
    warnings: list[str] = []
    by_id = {r["rule_id"]: r for r in old}
    old_by_path = {r["path"]: r for r in old}
    out, added, kept, renamed = [], [], [], []
    for r in new:
        prev = old_by_path.get(r["path"]) or by_id.get(r["rule_id"])
        if prev is not None:
            r = {**r, "rule_id": prev["rule_id"]}
            if (prev["path"], prev["label"]) != (r["path"], r["label"]):
                renamed.append(f"{prev['rule_id']}: {prev['path']} {prev['label']!r} → {r['path']} {r['label']!r}")
                if not accept_renames:
                    r = {**r, "path": prev["path"], "label": prev["label"]}
            kept.append(r["rule_id"])
        else:
            added.append(r["rule_id"])
        out.append(r)
    seen = {r["rule_id"] for r in out}
    removed = []
    for r in old:
        if r["rule_id"] not in seen:
            removed.append(r["rule_id"])
            out.append({**r, "status": "removed"})
    if renamed and not accept_renames:
        warnings += [f"not renamed (use --accept-renames): {x}" for x in renamed]
    ids = [r["rule_id"] for r in out]
    for rid in sorted({x for x in ids if ids.count(x) > 1}):
        raise UserError(f"two properties would have rule id {rid}")
    return out, {"added": added, "kept": kept, "removed": removed, "renamed": renamed if accept_renames else []}, \
        warnings


# --- the CLI -------------------------------------------------------------------------------------------
def cmd_sync(args) -> int:
    rows, required = sheet_rows(args.source)
    new, warnings = from_sheet(rows, required)
    merged, diff, more = merge(load(), new, args.accept_renames)
    write(merged)
    print(f"{FILE.name}: {len([r for r in merged if r['status'] != 'removed'])} properties · added "
          f"{len(diff['added'])} · kept {len(diff['kept'])} · removed {len(diff['removed'])}"
          + (f" · renamed {len(diff['renamed'])}" if diff["renamed"] else ""))
    for k in ("added", "removed", "renamed"):
        for x in diff[k]:
            print(f"  {k}: {x}")
    for w in warnings + more:
        print(f"  warning: {w}", file=sys.stderr)
    print("Review the diff, then run `golden-datasets properties apply --all`.")
    return 0


def cmd_list(args) -> int:
    rows = load()
    head = ("rule_id", "label", "path", "list", "req", "row", "status")
    table = [(r["rule_id"], r["label"], shown(r["path"]) or "—", "list" if r["multiple"] else "",
              "course key" if r["course_key"] else "req" if r["required"] else "", str(r["sheet_row"] or ""),
              r["status"]) for r in rows]
    widths = [max(len(h), *(len(t[i]) for t in table)) for i, h in enumerate(head)]
    for t in (head, *table):
        print("  ".join(c.ljust(w) for c, w in zip(t, widths)).rstrip())
    return 0


# --- apply: the file's new properties into each catalog (§4.1, §4.6) ----------------------------------------
COURSE_LOCATOR = "locator-course-page"


def course_locator(rules: dict[str, dict], settings: dict) -> str | None:
    """The record locator of course pages: `locator-course-page`, else the one whose course key a rule reads."""
    if rules.get(COURSE_LOCATOR, {}).get("kind") == "locator":
        return COURSE_LOCATOR
    keyed = sorted((settings or {}).get("course_key_rule") or {})
    return keyed[0] if keyed else next((rid for rid in sorted(rules) if rules[rid]["kind"] == "locator"), None)


def missing_rules(rules: dict[str, dict], settings: dict) -> dict[str, dict]:
    """Drafts for the file's properties a catalog has no rule for (by rule id, or by path on course pages):
    `rule_type: none`, with the sheet's definition as its "what"."""
    loc = course_locator(rules, settings)
    if loc is None:
        return {}
    have_paths = {r.get("ctdl_property") for r in rules.values() if r["kind"] == "property"
                  and r["definition"].get("locator") == loc}
    have_labels = {r.get("property_label") for r in rules.values() if r["kind"] == "property"
                   and r["definition"].get("locator") == loc}
    out = {}
    for p in active():
        if p["rule_id"] in rules or (p["path"] and p["path"] in have_paths) or p["label"] in have_labels:
            continue
        out[p["rule_id"]] = {"rule_id": p["rule_id"], "kind": "property", "ctdl_property": p["path"] or None,
                             "property_label": p["label"], "definition": {"locator": loc, "rule_type": "none"},
                             "what": p["definition_text"], "how": "No rule yet.", "why": "", "examples": []}
    return out


def apply(ctx, by: str, log=lambda *a: None) -> dict | None:
    """One ruleset version with every property the catalog lacks, and its extraction (no values change). None when
    the catalog already has them all. The same version folds the six Estimated Duration rules into one list-of-objects
    rule (profiles_rule.fold_rules, sme-fixes §5.1)."""
    from . import extract, profiles_rule, rulesets

    if not ctx.ruleset_versions():
        return None
    latest = ctx.latest_ruleset()
    rs, base = ctx.ruleset_rules(latest)
    kept, folded, removed = profiles_rule.fold_rules(base)
    drafts = missing_rules(kept, rs["settings"])
    if not drafts and not folded and not removed:
        return None
    planned = rulesets.plan_versions(ctx, {**drafts, **folded}, base)
    note = "; ".join(x for x in (
        f"added {len(drafts)} property rules from the Phase 1 sheet" if drafts else "",
        f"Estimated Duration is one list of objects ({len(removed)} child rules folded in)" if removed else "") if x)
    doc = rulesets.publish(ctx, {**kept, **planned}, rs["settings"], note, by)
    meta = extract.extract(ctx, doc["version"], created_by=by, log=log)
    return {"ruleset_version": doc["version"], "added": sorted(drafts), "folded": sorted(folded), "removed": removed,
            "extraction": meta["extraction"]}


def cmd_apply(args) -> int:
    from . import manifest
    from .catalogs import resolve
    from .context import Ctx
    from .storage import open_root

    root = open_root(args.root)
    if args.catalog:
        catalogs = [resolve(args.catalog)]
    else:
        doc, _ = manifest.load(root)
        catalogs = [c["catalog"] for c in doc["catalogs"] if c.get("rulesets")]
    for catalog in catalogs:
        out = apply(Ctx(root, catalog), args.by, log=lambda m: print(m, file=sys.stderr))
        if out is None:
            print(f"{catalog}: every property already has a rule (nothing published)")
        else:
            print(f"{catalog}: ruleset v{out['ruleset_version']} adds {len(out['added'])} property rules with no "
                  f"rule yet · {out['extraction']}")
            if out["removed"]:
                print(f"  folded into a list of objects: {', '.join(out['folded']) or 'nothing (no rule yet)'}; "
                      f"removed: {', '.join(out['removed'])}")
    return 0
