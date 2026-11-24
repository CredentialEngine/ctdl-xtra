"""The property lists (property-rules spec §4.1; LearningProgram spec, approved items 2–4): one file per class,
`properties/<class>.csv`, synced from that class's tab of "xTRA: Learning Opportunity BU Template"
(`<Name> Properties`: `Course Properties`, `Learning Program Properties`), plus Learning Type.

The app never reads the sheet at run time:
- `golden-datasets properties sync --class X` writes the file from the sheet (the diff is reviewed like code);
- `golden-datasets properties list --class X` prints it;
- `golden-datasets properties apply --class X` adds the file's new properties to each catalog, with no rule yet (§4.6).

**Tiers.** Every class has three: Required (the class's CTDL-required properties, `classes.REQUIRED` until the sheet
gets a Required column), then the rest of Phase 1, then Phase 2. Phase is the sheet's xTRA Status column.

**The record key** is the External Identifier (`ceterms:identifier`, issue #368) for every class: the row with
`record_key` true.

Paths are stored as the sheet writes them (`ceterms:creditValue>schema:minValue`) and shown to people with arrows.
"""

from __future__ import annotations

import csv
import io
import re
import sys
import urllib.request
import zipfile
from datetime import date as date_type
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

from . import classes
from .classes import CtdlClass
from .errors import UserError

FOLDER = Path(__file__).with_name("properties")
SHEET_XLSX = ("https://docs.google.com/spreadsheets/d/1zFG1Qzn4NTrvb5KTxucKnz-gPd8H_W0oYYRdh7jT8ro/export"
              "?format=xlsx")
COLUMNS = ["rule_id", "path", "sheet_path", "path_note", "label", "parent", "profile", "multiple", "required",
           "phase", "record_key", "sheet_row", "status", "vocabulary", "definition_text", "sample"]
BOOLS = ("multiple", "required", "record_key")
RECORD_KEY = "ceterms:identifier"
PHASES = ("Phase 1", "Phase 2")
#: The Rules tab's tiers, in order (approved item 3).
TIERS = (("required", "Required"), ("phase1", "Phase 1"), ("phase2", "Phase 2"))
#: Course's rule ids from before the sheet named them by path (§4.1), after the class prefix; every class uses them,
#: so the same property has the same id in each (`learningprogram-external-id`). Other ids come from the path.
KEPT_IDS = {"ceterms:codedNotation": "code", "ceterms:identifier": "external-id", "ceterms:name": "name",
            "ceterms:description": "description", "ceterms:subjectWebpage": "subject-webpage",
            "ceterms:lifeCycleStatusType": "lifecycle", "ceterms:inLanguage": "language"}
#: Names the sheet's column D doesn't give yet (phase1-followups spec §2.1): drop an entry once column D says it.
LABELS = {"ceterms:creditValue>schema:value": "Credit Unit Value"}
#: Rows the sheet writes in a way sync doesn't take as written (§4.1).
SKIP_PATHS = {"ceterms:learningOpportunityType": "removed from the sheet (W3): not a CTDL property",
              # Estimated Duration is one list-of-objects rule (sme-fixes §5.1): its children are fields, not rules
              **{f"ceterms:estimatedDuration>{c}": "a field of the Estimated Duration list (profiles_rule.py)"
                 for c in ("ceterms:description", "ceterms:exactDuration", "ceterms:minimumDuration",
                           "ceterms:maximumDuration", "ceterms:timeRequired")}}
#: The sheet's columns, by header (each class's tab has its own extra columns, such as Value Type).
HEADERS = {"status": "xTRA Status", "profile": "Subclass", "label": "CTDL Property Label",
           "shorthand": "CTDL Shorthand URI", "cli": "CLI Extraction Label", "definition": "Definition",
           "vocabulary": "Controlled Vocabulary", "multiple": "Multiple Values", "sample": "Sample",
           "required": "Required"}
_PATH = re.compile(r"[a-z]+:[A-Za-z]+(>[a-z]+:[A-Za-z]+)*")


def learning_type(cls: CtdlClass | str) -> dict:
    """Learning Type isn't on the sheet: a constant rule with no path, the class's name (§4.1)."""
    c = classes.get(cls)
    return {"rule_id": f"{c.rule_prefix}learning-type", "path": "", "sheet_path": "", "path_note": "",
            "label": "Learning Type", "parent": "", "profile": "", "multiple": False, "required": True,
            "phase": "Phase 1", "record_key": False, "sheet_row": 0, "status": "Include", "vocabulary": "",
            "sample": c.name,
            "definition_text": f"The type of learning opportunity. Always {c.name} here (the Studio's own column)."}


# --- reading -------------------------------------------------------------------------------------------
def file_of(cls: CtdlClass | str) -> Path:
    return FOLDER / f"{classes.get(cls).slug}.csv"


def _bool(v) -> bool:
    return v is True or str(v).strip().lower() == "true"


@lru_cache(maxsize=8)
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


def load(cls: CtdlClass | str, path: Path | None = None) -> list[dict]:
    """Every row of the class's file, in sheet order (Learning Type, with no sheet row, first)."""
    p = path or file_of(cls)
    if not p.exists():
        return []
    return [dict(r) for r in _load(str(p), p.stat().st_mtime)]


def active(cls: CtdlClass | str, path: Path | None = None) -> list[dict]:
    """The rows still on the sheet (not `removed`)."""
    return [r for r in load(cls, path) if r["status"] != "removed"]


def write(rows: list[dict], cls: CtdlClass | str, path: Path | None = None) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("true" if r[k] else "false") if k in BOOLS else r.get(k, "") for k in COLUMNS})
    p = path or file_of(cls)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(buf.getvalue())


def tier(row: dict) -> str:
    """`required`, `phase1` or `phase2` (approved item 3)."""
    if row.get("required"):
        return "required"
    return "phase2" if row.get("phase") == "Phase 2" else "phase1"


def required_order(cls: CtdlClass | str) -> tuple[str, ...]:
    """The Rules tab's fixed order for a class's required properties (§4.8): the record key first."""
    return classes.get(cls).required


def shown(path: str | None) -> str:
    """A path for people: `ceterms:creditValue → schema:minValue` (R8)."""
    return (path or "").replace(">", " → ")


def leaf(path: str | None) -> str:
    return (path or "").rsplit(">", 1)[-1]


def label_of(path: str) -> str:
    """A term in words, for a flat row with no name: `ceterms:hasPart` → `Has Part`."""
    term = leaf(path).split(":", 1)[-1]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", term)[:1].upper() + re.sub(r"(?<=[a-z])(?=[A-Z])", " ", term)[1:]


def rule_id_for(path: str, cls: CtdlClass | str = "course") -> str:
    """A new property's rule id, from its path and class: `ceterms:creditValue>schema:minValue` →
    `course-credit-value-min-value`, `ceterms:name` → `learningprogram-name`."""
    c = classes.get(cls)
    if path in KEPT_IDS:
        return c.rule_prefix + KEPT_IDS[path]
    parts = [re.sub(r"(?<=[a-z])(?=[A-Z])", "-", p.split(":", 1)[-1]).lower() for p in path.split(">")]
    return c.rule_prefix + "-".join(parts)


# --- the sheet -----------------------------------------------------------------------------------------
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


#: Built-in number formats that are dates (ECMA-376 §18.8.30).
_DATE_FORMATS = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}


def _date_styles(z: zipfile.ZipFile) -> set[int]:
    """The cell style indexes whose number format is a date."""
    if "xl/styles.xml" not in z.namelist():
        return set()
    root = ET.fromstring(z.read("xl/styles.xml"))
    custom = {int(f.get("numFmtId")) for f in root.iter(f"{{{_NS['m']}}}numFmt")
              if re.search(r"[dmy]", re.sub(r'"[^"]*"|\\.|\[[^]]*\]', "", f.get("formatCode") or ""), re.I)}
    xfs = root.find("m:cellXfs", _NS)
    return {i for i, xf in enumerate(xfs if xfs is not None else [])
            if int(xf.get("numFmtId") or 0) in _DATE_FORMATS | custom}


def _cell_text(v: str, kind: str | None, date: bool) -> str:
    """A value cell as the sheet shows it: TRUE / FALSE, a date as YYYY-MM-DD, a whole number without `.0`."""
    if kind == "b":
        return "TRUE" if v == "1" else "FALSE"
    if kind in (None, "n") and v:
        try:
            x = float(v)
        except ValueError:
            return v
        if date:
            return (date_type(1899, 12, 30) + timedelta(days=int(x))).isoformat()
        return str(int(x)) if x.is_integer() else v
    return v


def read_xlsx(data: bytes) -> dict[str, list[list[str]]]:
    """Every tab of an xlsx file as rows of text, as the sheet shows it (no library: the sheet only needs cell
    text)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    dates = _date_styles(z)
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
                    text = _cell_text(v.text if v is not None and v.text else "", c.get("t"),
                                      int(c.get("s") or 0) in dates)
                cells += [""] * (i - len(cells)) + [text]
            rows.append(cells)
        out[sheet.get("name")] = rows
    return out


def sheet_rows(source: str | None, cls: CtdlClass | str) -> list[list[str]]:
    """The class's tab, as rows of text (row 1 is the header): from a CSV export of the tab, an xlsx export of the
    sheet, or the sheet itself."""
    c = classes.get(cls)
    if source and source.lower().endswith(".csv"):
        with open(source, newline="") as fh:
            return list(csv.reader(fh))
    if source:
        data = Path(source).read_bytes()
    else:
        with urllib.request.urlopen(SHEET_XLSX, timeout=60) as resp:
            data = resp.read()
    tabs = read_xlsx(data)
    if c.sheet_tab not in tabs:
        raise UserError(f"the workbook has no {c.sheet_tab!r} tab (tabs: {', '.join(tabs)})")
    return tabs[c.sheet_tab]


def _columns(header: list[str]) -> dict[str, int]:
    at = {h.strip().lower(): i for i, h in enumerate(header) if h and h.strip()}
    cols = {k: at[h.lower()] for k, h in HEADERS.items() if h.lower() in at}
    missing = [HEADERS[k] for k in ("status", "label", "shorthand", "cli") if k not in cols]
    if missing:
        raise UserError(f"the tab has no {', '.join(repr(m) for m in missing)} column (header: {', '.join(header)})")
    return cols


def from_sheet(rows: list[list[str]], cls: CtdlClass | str) -> tuple[list[dict], list[str]]:
    """The file's rows from the class's tab (row 1 is the header, read by name), and warnings. The path is the CLI
    Extraction Label, else the CTDL Shorthand URI; Phase is xTRA Status; Required is the tab's Required column if it
    has one, else the class's CTDL-required list."""
    c = classes.get(cls)
    warnings: list[str] = []
    cols = _columns(rows[0] if rows else [])
    sheet_required = "required" in cols
    if not sheet_required:
        warnings.append(f"no Required column: required properties are {c.name}'s CTDL-required list")
    got: list[dict] = []
    multiple_of: dict[str, bool] = {}
    for n, r in enumerate(rows[1:], start=2):
        def cell(key: str, r: list[str] = r) -> str:
            i = cols.get(key)
            return r[i].strip() if i is not None and i < len(r) and r[i] else ""
        cli, short = cell("cli"), cell("shorthand")
        if not cli and not short:
            continue
        path = cli
        if not _PATH.fullmatch(cli):
            if not _PATH.fullmatch(short):
                warnings.append(f"row {n}: no CTDL path in {HEADERS['cli']!r} or {HEADERS['shorthand']!r}; skipped")
                continue
            if cli:
                warnings.append(f"row {n}: {HEADERS['cli']!r} isn't a path; read {short} from "
                                f"{HEADERS['shorthand']!r}")
            path = short
        if path in SKIP_PATHS:
            warnings.append(f"row {n}: {path} skipped: {SKIP_PATHS[path]}")
            continue
        phase = cell("status")
        if phase not in PHASES:
            warnings.append(f"row {n}: xTRA Status {phase!r} isn't Phase 1 or Phase 2; read as Phase 2")
            phase = "Phase 2"
        got.append({"sheet_row": n, "sheet_path": path, "path": path, "path_note": "", "profile": cell("profile"),
                    "column_d": cell("label"), "phase": phase, "definition_text": cell("definition"),
                    "vocabulary": cell("vocabulary"), "single_multiple": cell("multiple"), "sample": cell("sample"),
                    "required_cell": cell("required")})
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
    # Single / Multiple: blank rows copy the Prerequisite group's shape (P4).
    for g in got:
        sm = g["single_multiple"].lower()
        if sm in ("single", "multiple"):
            multiple_of[g["path"]] = sm == "multiple"
            continue
        multiple_of[g["path"]] = ">" not in g["path"] or leaf(g["path"]) != "ceterms:description"
        warnings.append(f"row {g['sheet_row']}: no Single / Multiple; read as "
                        f"{'Multiple' if multiple_of[g['path']] else 'Single'} like the Prerequisite group (P4)")
    out = [learning_type(c)]
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
        required = _bool(g["required_cell"]) or g["required_cell"].lower() in ("yes", "required") \
            if sheet_required else path in c.required
        out.append({"rule_id": rule_id_for(path, c), "path": path, "sheet_path": g["sheet_path"],
                    "path_note": g["path_note"], "label": label, "parent": parent, "profile": g["profile"],
                    "multiple": multiple_of[path], "required": required, "phase": g["phase"],
                    "record_key": path == RECORD_KEY, "sheet_row": g["sheet_row"], "status": "Include",
                    "vocabulary": g["vocabulary"], "definition_text": g["definition_text"], "sample": g["sample"]})
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
    c = classes.get(args.cls)
    new, warnings = from_sheet(sheet_rows(args.source, c), c)
    merged, diff, more = merge(load(c), new, args.accept_renames)
    write(merged, c)
    print(f"properties/{c.slug}.csv: {len([r for r in merged if r['status'] != 'removed'])} properties, added "
          f"{len(diff['added'])}, kept {len(diff['kept'])}, removed {len(diff['removed'])}"
          + (f", renamed {len(diff['renamed'])}" if diff["renamed"] else ""))
    for k in ("added", "removed", "renamed"):
        for x in diff[k]:
            print(f"  {k}: {x}")
    for w in warnings + more:
        print(f"  warning: {w}", file=sys.stderr)
    print(f"Review the diff, then run `golden-datasets properties apply --class {c.slug} --all`.")
    return 0


def cmd_list(args) -> int:
    rows = load(args.cls)
    head = ("rule_id", "label", "path", "list", "tier", "key", "row", "status")
    names = dict(TIERS)
    table = [(r["rule_id"], r["label"], shown(r["path"]) or "—", "list" if r["multiple"] else "",
              names[tier(r)], "record key" if r["record_key"] else "", str(r["sheet_row"] or ""), r["status"])
             for r in rows]
    widths = [max(len(h), *(len(t[i]) for t in table)) for i, h in enumerate(head)]
    for t in (head, *table):
        print("  ".join(c.ljust(w) for c, w in zip(t, widths)).rstrip())
    return 0


# --- apply: the file's new properties into each catalog (§4.1, §4.6) ----------------------------------------
def record_locator(rules: dict[str, dict], cls: CtdlClass | str) -> str | None:
    """The record locator of a class's pages: `locator-<class>-page` (`locator-course-page`), else the locator the
    class's External Identifier rule reads; for Course, else the first locator."""
    c = classes.get(cls)
    named = f"locator-{c.slug}-page"
    if rules.get(named, {}).get("kind") == "locator":
        return named
    keyed = sorted(r["definition"].get("locator") for rid, r in rules.items() if r["kind"] == "property"
                   and rid.startswith(c.rule_prefix) and r.get("ctdl_property") == RECORD_KEY
                   and r["definition"].get("locator"))
    if keyed:
        return keyed[0]
    if c.slug == "course":
        return next((rid for rid in sorted(rules) if rules[rid]["kind"] == "locator"), None)
    return None


def missing_rules(rules: dict[str, dict], cls: CtdlClass | str) -> dict[str, dict]:
    """Drafts for the class's properties a catalog has no rule for (by rule id, or by path on the class's pages):
    `rule_type: none`, with the sheet's definition as its "what". None without a record locator for the class."""
    loc = record_locator(rules, cls)
    if loc is None:
        return {}
    have_paths = {r.get("ctdl_property") for r in rules.values() if r["kind"] == "property"
                  and r["definition"].get("locator") == loc}
    have_labels = {r.get("property_label") for r in rules.values() if r["kind"] == "property"
                   and r["definition"].get("locator") == loc}
    out = {}
    for p in active(cls):
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
    drafts = missing_rules(kept, ctx.cls)
    if not drafts and not folded and not removed:
        return None
    planned = rulesets.plan_versions(ctx, {**drafts, **folded}, base)
    note = "; ".join(x for x in (
        f"added {len(drafts)} property rules from the sheet's {ctx.ctdl_class.sheet_tab} tab" if drafts else "",
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
        out = apply(Ctx(root, catalog, cls=args.cls), args.by, log=lambda m: print(m, file=sys.stderr))
        if out is None:
            print(f"{catalog}: every property already has a rule (nothing published)")
        else:
            print(f"{catalog}: ruleset v{out['ruleset_version']} adds {len(out['added'])} property rules with no "
                  f"rule yet, {out['extraction']}")
            if out["removed"]:
                print(f"  folded into a list of objects: {', '.join(out['folded']) or 'nothing (no rule yet)'}; "
                      f"removed: {', '.join(out['removed'])}")
    return 0
