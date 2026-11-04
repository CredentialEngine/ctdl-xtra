"""Scores (Evals spec §4): one extract output compared with one golden dataset by xtra's own scorer, and kept.

    <crawl>/golden-dataset-studio/scores/sc-NNNN/{score.json, values.parquet}
    <crawl>/golden-dataset-studio/extract-outputs/<report last modified>/{records/, extract-report.json}

**The scorer** is xtra-cli's (`match_extraction_run`, a uv path dependency on `../xtra-cli`), called in-process with
two store adapters (`list_keys`, `get_json`, `describe_location`): `RecordsStore` reads an extract output's
`records/` where it is, and never writes; `GoldenStore` serves a golden dataset from memory, as the scorer reads it
(`<catalog>/<crawl>/<stem>/<stem>.json`). Nothing is written next to the records: the reports stay in memory.

**A golden dataset** is `ruleset-vN` (its version's two trees in the golden root), `human-reviewed` (the latest
version's trees as they are now: each expert verdict rewrites a page's files, so `golden.parquet` would be stale) or a
draft `rs-NNNN` (an unpublished extraction, planned in memory into the same two trees). **Each score runs the scorer
twice**, exact and partial each time: on the `human-reviewed/` tree and on the `rule-matched/` tree, exactly as
`xtra score --baseline-uri …/ruleset-vN/<tree>` would. Both results are kept.

The trees hold only what the scorer accepts (`golden.tree_pages`: no values without a CTDL term, no empty records). A
value with `location: null` is implied, not on the page, and the scorer skips it (xtra-cli #343).

**An extract output** is what `xtra catalog extract` wrote for the crawl (`$GOLDEN_DATASETS_XTRA_SOURCE`, else the
shared container). xtra overwrites it in place, so the first time the Studio sees a report (by ETag) it copies
`records/` and the report into `extract-outputs/<report last modified>/`, and scores read that copy.

A pair (golden dataset content, extract output) is scored once: asking again returns the score there is.

**Units** (sme-fixes spec §8): the scorer compares values, objects (one `estimatedDuration` object per golden field)
and "not on the page" markers (`{"value": null, "absent": true}`), and gives each golden unit match · partial · wrong
· missing · unsure, and each extracted unit with no golden partner `extra`. values.parquet has one row per golden unit
and per extra, with its `unit`, the object `field`s that differ and a `reason`; `counts` gives found (recall: match ÷
golden values), right (precision: match ÷ candidates paired or extra) and the courses exact; `wrong_groups` is "Where
it's wrong".
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa

from . import golden as golden_mod
from . import layout, manifest, model
from .context import Ctx
from .errors import UserError
from .storage import AzureRoot, Root, open_root

SHARED_XTRA_ROOT = "azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output"
HUMAN_REVIEWED = golden_mod.HUMAN_REVIEWED
BASES = ("human", "rule")  # the human-reviewed values only; every rule-matched value
TREE = {"human": golden_mod.HUMAN_REVIEWED, "rule": golden_mod.RULE_MATCHED}  # each basis's tree
#: A golden unit's outcome (sme-fixes spec §8.1), worst first; `extra` is an extracted unit with no golden partner.
GOLDEN_OUTCOMES = ("missing", "wrong", "partial", "unsure", "match")
OUTCOMES = (*GOLDEN_OUTCOMES, "extra")
SLOT_NAMES = "this output uses slot names; re-extract with the current xtra-cli"
#: values.parquet: model.SCORE_VALUES plus what a unit is (value · object · absent), the object fields that differ
#: (comma-separated, prefix-free) and why it isn't a match (`reason`, see `reason_for`).
SCORE_VALUES = pa.schema([*model.SCORE_VALUES, ("unit", pa.string()), ("field", pa.string()), ("reason", pa.string())])


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def column(ctdl_property: str) -> str:
    """The column's name in Evals: the CTDL path without prefixes (`creditValue>minValue`); shown with arrows."""
    return ">".join(t.split(":", 1)[-1] for t in ctdl_property.split(">"))


def _text(v) -> str | None:
    if v is None:
        return None
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


# --- store adapters ----------------------------------------------------------------------------------
class RecordsStore:
    """An extract output (`records/`, `extract-report.json`) under `base` in `root`, as the scorer sees it at
    `<catalog>/<crawl>/…`. Read-only; records are read once and kept for the next run."""

    def __init__(self, root: Root, base: str, catalog: str, crawl: str):
        self.root, self.base, self.prefix = root, base.strip("/"), f"{catalog}/{crawl}"
        self._json: dict[str, object] = {}

    def _path(self, key: str) -> str:
        key = key.strip("/")
        if key != self.prefix and not key.startswith(self.prefix + "/"):
            raise FileNotFoundError(key)
        return "/".join(p for p in (self.base, key[len(self.prefix):].strip("/")) if p)

    def list_keys(self, under: str = "") -> list[str]:
        try:
            path = self._path(under)
        except FileNotFoundError:
            return []
        cut = len(self.base) + 1 if self.base else 0
        return [f"{self.prefix}/{p[cut:]}" for p in self.root.list(path)]

    def get_json(self, key: str) -> object:
        if key not in self._json:
            self._json[key] = self.root.read_json(self._path(key))
        return self._json[key]

    def describe_location(self) -> str:
        return "/".join(p for p in (self.root.uri, self.base) if p)

    def records(self) -> list[str]:
        return [k for k in self.list_keys(f"{self.prefix}/records") if k.endswith(".json")]


class GoldenStore:
    """A golden dataset's pages {stem: entities}, served from memory at `<catalog>/<crawl>/<stem>/<stem>.json`."""

    def __init__(self, pages: dict[str, list[dict]], catalog: str, crawl: str, where: str):
        self.pages, self.prefix, self.where = pages, f"{catalog}/{crawl}", where

    def list_keys(self, under: str = "") -> list[str]:
        under = under.strip("/")
        return [k for k in (f"{self.prefix}/{s}/{s}.json" for s in sorted(self.pages)) if k.startswith(under)]

    def get_json(self, key: str) -> object:
        parts = key.strip("/").split("/")
        if len(parts) < 2 or parts[-2] not in self.pages:
            raise FileNotFoundError(key)
        return self.pages[parts[-2]]

    def describe_location(self) -> str:
        return self.where


def is_implied(f: dict) -> bool:
    """Implied, not printed on the page: not scored. An absent field (`absent: true`, not on the page) is scored."""
    return "location" in f and f["location"] is None and f.get("absent") is not True


# --- golden datasets ---------------------------------------------------------------------------------
@dataclass
class Golden:
    id: str                                  # ruleset-vN, human-reviewed or rs-NNNN
    kind: str                                # version, human-reviewed or draft
    where: str                               # where the trees are (or the extraction, for a draft)
    trees: dict[str, dict[str, list[dict]]]  # basis → the pages of its tree, as the scorer reads them
    left_out: dict[str, list[dict]] = field(default_factory=dict)  # basis → pages its tree leaves out (with why)
    as_of: str = field(default_factory=_now)
    baseline_uris: dict[str, str] | None = None  # basis → what `xtra score --baseline-uri` reads

    @functools.cached_property
    def sha256(self) -> str:
        return hashlib.sha256(model.canon(self.trees).encode()).hexdigest()


def _read_pages(root: Root, prefix: str) -> dict[str, list[dict]]:
    """Every `<stem>/<stem>.json` below `prefix` that holds a course."""
    prefix = prefix.strip("/")
    paths = []
    for p in root.list(prefix):
        parts = p[len(prefix) + 1:].split("/")
        if len(parts) == 2 and parts[1] == f"{parts[0]}.json":
            paths.append(p)

    def one(p: str):
        doc = root.read_json(p)
        return p.rsplit("/", 2)[-2], [doc] if isinstance(doc, dict) else doc

    with ThreadPoolExecutor(max_workers=16) as pool:
        return {s: d for s, d in pool.map(one, paths) if d}


def latest_golden(ctx: Ctx) -> str | None:
    vs = golden_mod.versions(ctx)
    return golden_mod.version_name(max(vs)) if vs else None


def _human_left_out(rule: dict[str, list[dict]]) -> list[dict]:
    """The pages with human-reviewed values that the human-reviewed tree leaves out."""
    return golden_mod.tree_pages(rule, golden_mod.HUMAN_REVIEWED)[1]


def load_golden(ctx: Ctx, gid: str) -> Golden:
    vs = golden_mod.versions(ctx)
    m = golden_mod.VERSION.match(gid)
    if gid == HUMAN_REVIEWED or m:
        if gid == HUMAN_REVIEWED and not vs:
            raise UserError(f"{ctx.catalog}: no golden dataset yet; an expert's first verdict creates one")
        n = max(vs) if gid == HUMAN_REVIEWED else int(m.group(1))
        if n not in vs:
            raise UserError(f"{gid}: no such golden dataset (published: "
                            f"{', '.join(golden_mod.version_name(v) for v in sorted(vs)) or 'none'})")
        root = open_root(vs[n]["to"])
        tree = {b: _read_pages(root, golden_mod.version_prefix(ctx, n, t)) for b, t in TREE.items()}
        uris = {b: f"{root.uri}/{golden_mod.version_root(ctx, n, t)}" for b, t in TREE.items()}
        where = f"{root.uri}/catalogs/{ctx.catalog}/versions/{golden_mod.version_name(n)}"
        return Golden(gid, "human-reviewed" if gid == HUMAN_REVIEWED else "version", where, tree,
                      {"human": _human_left_out(tree["rule"]), "rule": []}, baseline_uris=uris)
    if gid in {e["extraction"] for e in ctx.extractions()}:
        from .review import LOADER

        rule, left = golden_mod.tree_pages(golden_mod.plan(LOADER.review(ctx, gid))["pages"], golden_mod.RULE_MATCHED)
        human, _ = golden_mod.tree_pages(rule, golden_mod.HUMAN_REVIEWED)
        return Golden(gid, "draft", f"extraction {gid} (unpublished)", {"human": human, "rule": rule},
                      {"human": _human_left_out(rule), "rule": left})
    raise UserError(f"{gid}: not a golden dataset (ruleset-vN, {HUMAN_REVIEWED} or a draft rs-NNNN)")


# --- extract outputs ---------------------------------------------------------------------------------
def xtra_source(root: Root) -> str:
    """Where xtra-cli writes extract outputs: $GOLDEN_DATASETS_XTRA_SOURCE, else the shared container."""
    src = os.environ.get("GOLDEN_DATASETS_XTRA_SOURCE")
    if src:
        return src
    if isinstance(root, AzureRoot):
        return SHARED_XTRA_ROOT
    raise UserError("set GOLDEN_DATASETS_XTRA_SOURCE to the xtra-cli output root (a folder, or azure://…/xtra-cli-output)")


def outputs(ctx: Ctx) -> list[dict]:
    """The extract outputs the Studio has seen (and copied), oldest first."""
    return list(ctx.crawl_entry().get("extract_outputs", []))


def _identity(root: Root, base: str, catalog: str, crawl: str) -> dict:
    """What identifies an extract output: its report's ETag and last-modified time, its counts."""
    path = "/".join(p for p in (base, "extract-report.json") if p)
    st = root.stat(path)
    if st is None:
        raise UserError(f"{root.uri}/{path}: no extract report")
    report = root.read_json(path)
    store = RecordsStore(root, base, catalog, crawl)
    n = len(store.records())
    modified = (st.modified or datetime.now(UTC)).astimezone(UTC)
    return {"id": modified.strftime("%Y-%m-%dT%H-%M-%SZ"), "path": store.describe_location(), "report_etag": st.etag,
            "last_modified": modified.strftime("%Y-%m-%dT%H:%M:%SZ"), "run_id": report.get("run_id"),
            "discovery_run_id": report.get("discovery_run_id"), "only_golden_sample": report.get("only_golden_sample"),
            "records": n, "records_written": report.get("records_written"),
            "records_mismatch": report.get("records_written") is not None and n != report.get("records_written")}


def see_output(ctx: Ctx, log=print) -> tuple[dict | None, bool]:
    """The latest extract output for the crawl (None if xtra hasn't written one), and whether it is new: the first
    time its report's ETag is seen, `records/` and the report are copied into extract-outputs/<id>/."""
    src = open_root(xtra_source(ctx.root))
    prefix = f"{ctx.catalog}/{ctx.crawl}"
    st = src.stat(f"{prefix}/extract-report.json")
    if st is None:
        return None, False
    known = next((o for o in outputs(ctx) if o["report_etag"] == st.etag), None)
    if known:
        return known, False
    ident = _identity(src, prefix, ctx.catalog, ctx.crawl)
    taken = {o["id"] for o in outputs(ctx)}
    base_id, n = ident["id"], 1
    while ident["id"] in taken:  # two outputs written within the same second
        n += 1
        ident["id"] = f"{base_id}-{n}"
    copy = layout.extract_output_dir(ctx.catalog, ctx.crawl, ident["id"])
    paths = [*src.list(f"{prefix}/records"), f"{prefix}/extract-report.json"]
    log(f"new extract output {ident['id']}: copying {len(paths):,} files into {copy}")

    def one(p: str) -> None:
        ctx.root.write_bytes(f"{copy}/{p[len(prefix) + 1:]}", src.read_bytes(p))

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(one, paths))
    entry = {**ident, "copy": copy, "seen_at": _now()}

    def change(m: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl)
        manifest.add_unique(k.setdefault("extract_outputs", []), entry, key=lambda o: o["report_etag"])

    manifest.update(ctx.root, change)
    ctx.invalidate()
    return entry, True


def resolve_output(ctx: Ctx, output: str | None, log=print) -> tuple[dict, RecordsStore]:
    """An extract output: None or `latest` (the one xtra wrote last, copied when new), a copy's id, or a folder that
    holds records/ and extract-report.json (a path or an azure:// URI, read in place)."""
    if output in (None, "latest"):
        entry, _ = see_output(ctx, log)
        if entry is None:
            raise UserError(f"{ctx.catalog}: xtra hasn't written an extract output for crawl {ctx.crawl} "
                            f"in {xtra_source(ctx.root)}")
        output = entry["id"]
    entry = next((o for o in reversed(outputs(ctx)) if o["id"] == output), None)
    if entry:
        return entry, RecordsStore(ctx.root, entry["copy"], ctx.catalog, ctx.crawl)
    root = open_root(output)
    base = "" if root.exists("extract-report.json") else f"{ctx.catalog}/{ctx.crawl}"
    return _identity(root, base, ctx.catalog, ctx.crawl), RecordsStore(root, base, ctx.catalog, ctx.crawl)


def uses_slot_names(store: RecordsStore) -> bool:
    """True when no record's `expected` has a `ceterms:` key: an extractor older than the slot-name mapping."""
    keys = store.records()
    for k in keys:
        if any(p.startswith("ceterms:") for p in (store.get_json(k).get("expected") or {})):
            return False
    return bool(keys)


# --- scoring -----------------------------------------------------------------------------------------
@functools.cache
def xtra_cli_commit() -> str | None:
    """The commit of the xtra-cli the scorer comes from (`+dirty` with uncommitted changes there)."""
    import implementations

    here = Path(implementations.__file__).resolve().parents[2]
    try:
        sha = subprocess.run(["git", "-C", str(here), "rev-parse", "HEAD"], capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(here), "status", "--porcelain", "--", "."], capture_output=True,
                               text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return sha + ("+dirty" if dirty else "")


def run_scorer(records: RecordsStore, pages: dict[str, list[dict]], catalog: str, crawl: str,
               where: str) -> dict[str, dict]:
    """xtra's scorer on these pages, exact and partial: {mode: report}."""
    from implementations.score_extraction_match import match_extraction_run

    store = GoldenStore(pages, catalog, crawl, where)
    return {mode: match_extraction_run(records, store, catalog, crawl, mode) for mode in ("exact", "partial")}


def _short(name: str) -> str:
    return name.split(":", 1)[-1]


def _words(v) -> list[str]:
    return str(v or "").casefold().split()


def diff_kind(golden, extracted) -> str:
    """How an extracted value differs from the golden one, by words: `cut short` (the extracted words are a run of the
    golden ones), `extra text` (the golden words are a run of the extracted ones) or `different`."""
    a, b = _words(golden), _words(extracted)

    def within(small: list[str], big: list[str]) -> bool:
        return bool(small) and len(small) < len(big) and any(big[i:i + len(small)] == small
                                                              for i in range(len(big) - len(small) + 1))
    if within(b, a):
        return "cut short"
    if within(a, b):
        return "extra text"
    return "different"


def unit_of(value, absent: bool = False) -> str:
    return "absent" if absent else "object" if isinstance(value, dict) else "value"


def _differing(o: dict) -> list[str]:
    """An object's fields that aren't exact, worst first."""
    fields = o.get("object_fields") or {}
    return [k for k, f in sorted(fields.items(), key=lambda kv: kv[1]["similarity"]) if not f["exact"]]


def reason_for(outcome: str, unit: str, o: dict | None = None, claimed_absent: bool = False,
               golden_absent: bool = False) -> str | None:
    """Why a unit isn't a match, in a few words (values.parquet `reason`):
    - wrong / partial: the word diff of the worst differing field (or the value): cut short · extra text · different;
    - missing: `nothing extracted`, `claimed not on the page` (the record's null against a golden value) or
      `a value where golden says not on the page`;
    - unsure: `no claim` (golden says not on the page; the record has no key);
    - extra: `no golden value`, `golden says not on the page`, or `claimed not on the page` (an extracted null)."""
    if outcome in ("wrong", "partial") and o is not None:
        fields = o.get("object_fields") or {}
        bad = _differing(o)
        if bad:
            f = fields[bad[0]]
            return diff_kind(f["baseline"], f["extracted"])
        return diff_kind(o.get("baseline_value"), o.get("extracted_value"))
    if outcome == "missing":
        if unit == "absent":
            return "a value where golden says not on the page"
        return "claimed not on the page" if claimed_absent else "nothing extracted"
    if outcome == "unsure":
        return "no claim"
    if outcome == "extra":
        if unit == "absent":
            return "claimed not on the page"
        return "golden says not on the page" if golden_absent else "no golden value"
    return None


def value_rows(basis: str, pages: dict[str, list[dict]], reports: dict[str, dict]) -> list[dict]:
    """One row per scored unit: every golden unit (a value, an object or an absent marker) and every extra (an
    extracted unit with no golden partner, sme-fixes spec §8). Every golden unit that isn't an exact match is in the
    exact report's outliers (with its similarity; partial is ≥ the threshold), the extras in its `extras`; the rest
    matched. The counts are checked against both reports."""
    from implementations.score_extraction_match import PARTIAL_THRESHOLD

    exact, partial = reports["exact"], reports["partial"]
    out_by: dict[tuple, list[dict]] = defaultdict(list)
    for o in exact["outliers"]:
        out_by[(o["stem"], o["entity"], o["ctdl_property"], _text(o["baseline_value"]))].append(o)
    extras = (exact.get("extras") or {}).get("outliers") or []
    claims = {(e["stem"], e["entity"], e["ctdl_property"]) for e in extras if e.get("unit") == "absent"}
    scored = {p["stem"] for p in exact["pages"]}
    rows = []

    def base(stem: str, ei: int, ent: dict, prop: str, f: dict | None) -> dict:
        loc = (f or {}).get("location") or {}
        first = next(iter(ent["fields"]), {})
        return {"basis": basis, "column": column(prop), "ctdl_property": prop,
                "property": (f or first).get("property"), "golden_record_id": ent.get("golden_record_id"),
                "page_stem": stem, "entity": ei, "source_url": (f or first).get("source_url"),
                "golden_css_path": loc.get("css_path"), "golden_char_start": loc.get("char_start"),
                "golden_char_end": loc.get("char_end"), "approval": (f or {}).get("approval"),
                "approved_by": (f or {}).get("approved_by"), "approved_at": (f or {}).get("approved_at")}

    for stem, ents in sorted(pages.items()):
        if stem not in scored:
            continue
        for ei, ent in enumerate(ents):
            for f in ent["fields"]:
                if is_implied(f):
                    continue
                prop, absent = f["ctdl_property"], f.get("absent") is True
                unit = unit_of(f["value"], absent)
                o = out_by[(stem, ei, prop, _text(f["value"]))]
                o = o.pop(0) if o else None
                field_ = None
                if o is None:
                    outcome, sim, got = "match", 1.0, _text(f["value"])
                elif o["outcome"] in ("missing", "unsure"):
                    outcome, sim, got = o["outcome"], None, None
                else:
                    sim = o["similarity"]
                    outcome, got = "partial" if sim >= PARTIAL_THRESHOLD else "wrong", _text(o["extracted_value"])
                    field_ = ",".join(_short(k) for k in _differing(o)) or None
                reason = reason_for(outcome, unit, o, claimed_absent=(stem, ei, prop) in claims)
                rows.append({**base(stem, ei, ent, prop, f), "outcome": outcome, "similarity": sim,
                             "golden_value": _text(f["value"]), "extracted_value": got, "unit": unit,
                             "field": field_, "reason": reason})
    for e in extras:
        ents = pages.get(e["stem"]) or []
        ent = ents[e["entity"]] if e["entity"] < len(ents) else {"fields": []}
        prop = e["ctdl_property"]
        golden_absent = any(f["ctdl_property"] == prop and f.get("absent") is True for f in ent["fields"])
        rows.append({**base(e["stem"], e["entity"], ent, prop, None), "outcome": "extra", "similarity": None,
                     "golden_value": None, "extracted_value": _text(e["extracted_value"]), "unit": e.get("unit"),
                     "field": None, "reason": reason_for("extra", e.get("unit") or "value", golden_absent=golden_absent)})
    got = Counter(r["outcome"] for r in rows)
    want = {"match": exact["outcomes"]["match"], "missing": exact["outcomes"]["missing"],
            "unsure": exact["outcomes"].get("unsure", 0), "partial": partial["outcomes"]["partial"],
            "wrong": partial["outcomes"]["wrong"], "extra": len(extras)}
    golden_rows = sum(got[o] for o in GOLDEN_OUTCOMES)
    if golden_rows != exact["fields_total"] or any(got[k] != v for k, v in want.items()):
        raise UserError(f"{basis}: rebuilt counts {dict(got)} of {len(rows)} don't match the scorer's {want} "
                        f"of {exact['fields_total']}")
    return rows


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def counts(rows: list[dict]) -> dict:
    """Some rows' numbers: `values` (golden units) and each outcome; `extracted` (match + partial + wrong + extra);
    `found` (recall) = match ÷ values, `right` (precision) = match ÷ extracted; `courses` and `courses_exact` (courses
    whose every unit here matched); `list` when a course has several units or an object (a list property)."""
    c = Counter(r["outcome"] for r in rows)
    golden = sum(c[o] for o in GOLDEN_OUTCOMES)
    extracted = c["match"] + c["partial"] + c["wrong"] + c["extra"]
    by_course: dict[tuple, list[str]] = defaultdict(list)
    for r in rows:
        by_course[(r["page_stem"], r["entity"])].append(r["outcome"])
    return {"values": golden, **{o: c[o] for o in OUTCOMES}, "extracted": extracted,
            "found": _ratio(c["match"], golden), "right": _ratio(c["match"], extracted),
            "courses": len(by_course), "courses_exact": sum(all(o == "match" for o in v) for v in by_course.values()),
            "list": any(len([o for o in v if o != "extra"]) > 1 for v in by_course.values())
            or any(r.get("unit") == "object" for r in rows)}


def result(pages: dict[str, list[dict]], left_out: list[dict], reports: dict[str, dict], rows: list[dict]) -> dict:
    """One basis's result: the scorer's counts, per column too, with found, right and the courses exact."""
    exact = reports["exact"]
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["column"]].append(r)
    implied: Counter = Counter(column(f["ctdl_property"]) for ents in pages.values() for e in ents
                               for f in e["fields"] if is_implied(f))
    total = counts(rows)
    return {"values": exact["fields_total"], "exact_match_rate": exact["exact_match_rate"],
            "outcomes": {o: total[o] for o in OUTCOMES}, "found": exact.get("found"), "right": exact.get("right"),
            "extracted": total["extracted"], "entities_exact": exact.get("entities_exact"),
            "by_column": {col: counts(rs) for col, rs in sorted(by.items())},
            "implied": dict(sorted(implied.items())), "pages_scored": exact["pages_scored"],
            "pages_skipped": exact["pages_skipped"], "pages_out_of_scope": exact["pages_out_of_scope"],
            "malformed": len(exact["malformed"]), "left_out": left_out}


def commands(ctx: Ctx, g: Golden, output: dict) -> list[str]:
    """The `xtra score` commands for the two results: the human-reviewed tree, then the rule-matched tree (none for
    a draft: it has no files)."""
    if not g.baseline_uris:
        return []
    src = output["path"].removesuffix(f"/{ctx.catalog}/{ctx.crawl}")
    return [f"xtra score extraction match --exactly \\\n  --source-uri {src} \\\n  --baseline-uri {g.baseline_uris[b]} \\\n"
            f"  --catalog-id {ctx.catalog} \\\n  --run-id {ctx.crawl}" for b in BASES]


# --- score documents ---------------------------------------------------------------------------------
def score_ids(ctx: Ctx) -> list[str]:
    return [s["id"] for s in ctx.crawl_entry().get("scores", [])]


def read(ctx: Ctx, sid: str) -> dict:
    if sid not in score_ids(ctx):
        raise UserError(f"{sid}: no such score")
    return ctx.read_json(f"{layout.score_dir(ctx.catalog, ctx.crawl, sid)}/score.json", immutable=False)


def all_scores(ctx: Ctx) -> list[dict]:
    """Every score of the crawl, newest first."""
    ids = score_ids(ctx)
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda s: read(ctx, s), reversed(ids)))


def values(ctx: Ctx, sid: str) -> list[dict]:
    return ctx.rows(f"{layout.score_dir(ctx.catalog, ctx.crawl, sid)}/values.parquet")


def _write(ctx: Ctx, doc: dict, **kw) -> None:
    ctx.root.write_json(f"{layout.score_dir(ctx.catalog, ctx.crawl, doc['id'])}/score.json", doc, **kw)


@dataclass
class Prepared:
    golden: Golden
    output: dict
    records: RecordsStore
    pair: str


def prepare(ctx: Ctx, golden: str | None, output: str | None = None, log=print) -> Prepared:
    """Read the golden dataset and find the extract output (copying it when new); no score yet."""
    gid = golden or latest_golden(ctx)
    if not gid:
        raise UserError(f"{ctx.catalog}: no golden dataset yet; approve a column, or score --{HUMAN_REVIEWED}")
    g = load_golden(ctx, gid)
    out, store = resolve_output(ctx, output, log)
    return Prepared(g, out, store, f"{g.id}@{g.sha256[:16]}|{out['report_etag']}")


def existing(ctx: Ctx, p: Prepared) -> dict | None:
    """The score of this pair (the same golden content and extract output), unless it failed or was interrupted."""
    for doc in all_scores(ctx):
        if doc.get("pair") == p.pair and doc["status"] in ("running", "done"):
            return doc
    return None


def begin(ctx: Ctx, p: Prepared, by: str, reason: str) -> dict:
    """score.json with status `running`, registered in the manifest."""
    ctx.invalidate()  # the server's manifest may be a few seconds old
    ids = score_ids(ctx)
    sid = f"sc-{max((int(i.split('-')[1]) for i in ids), default=0) + 1:04d}"
    doc = {"id": sid, "status": "running", "pair": p.pair, "created_at": _now(), "finished_at": None, "by": by,
           "reason": reason, "error": None,
           "golden": {"id": p.golden.id, "kind": p.golden.kind, "from": p.golden.where, "as_of": p.golden.as_of,
                      "sha256": p.golden.sha256},
           "output": p.output, "slot_names": None, "scorer": {"xtra_cli_commit": xtra_cli_commit()},
           "commands": commands(ctx, p.golden, p.output), "columns": [], "results": {}}
    _write(ctx, doc, if_none_match=True)

    def change(m: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl)
        manifest.add_unique(k.setdefault("scores", []), {"id": sid}, key=lambda s: s["id"])

    manifest.update(ctx.root, change)
    ctx.invalidate()
    return doc


def candidates(records: RecordsStore) -> Counter:
    """column → the candidates an extract output has for it: its values (each item of a list, each object), as xtra's
    scorer reads the records. A property it claims is not on the page (an explicit null) is there with 0."""
    from implementations.score_extraction_match import extracted_claims

    out: Counter = Counter()
    for key in records.records():
        rec = records.get_json(key)
        if isinstance(rec, dict):
            pool, absent = extracted_claims(rec)
            for prop, vals in pool.items():
                out[prop] += len(vals)
            for prop in absent:
                out[prop] += 0
    return out


def emitted(records: RecordsStore) -> set[str]:
    """The CTDL properties an extract output emits (as xtra's scorer reads its records): with a value, or claimed not
    on the page (null)."""
    return set(candidates(records))


@functools.cache
def xtra_terms() -> frozenset[str]:
    """The CTDL properties xtra's extract writes at all (its TERMS, the identifier and the subject webpage): a column
    outside it is one "xtra doesn't extract". Empty when xtra-cli's extract can't be imported."""
    try:
        from implementations.extract import IDENTIFIER, SUBJECT_WEBPAGE, TERMS
    except Exception:  # noqa: BLE001 - only the wording of an unscored column depends on it
        return frozenset()
    return frozenset({*TERMS.values(), IDENTIFIER, SUBJECT_WEBPAGE})


def only_emitted(pages: dict[str, list[dict]], props: set[str]) -> dict[str, list[dict]]:
    """A tree with only the values of properties the extract output emits under the same path (P10): a column xtra
    never tries isn't scored against it."""
    out = {}
    for stem, ents in pages.items():
        kept = [{**e, "fields": [f for f in e["fields"] if f.get("ctdl_property") in props]} for e in ents]
        kept = [e for e in kept if e["fields"]]
        if kept:
            out[stem] = kept
    return out


def finish(ctx: Ctx, doc: dict, p: Prepared, log=print) -> dict:
    """Run the scorer on both bases, write values.parquet, and mark the score done (or failed). Only the columns
    the extract output emits are scored (property-rules spec P10); `not_scored` lists the others, and each basis's
    `xtra` keeps the scorer's own numbers over every column."""
    try:
        doc["slot_names"] = uses_slot_names(p.records)
        rows: list[dict] = []
        sizes = {}
        found = candidates(p.records)
        props = set(found)
        # the candidates per column (Evals: "N candidates"), and the columns xtra's extract writes at all
        doc["candidates"] = {column(k): n for k, n in sorted(found.items())}
        doc["xtra_extracts"] = sorted(column(t) for t in xtra_terms())
        if doc["slot_names"]:  # an old output names no CTDL paths: score every column, as before, and say so
            props |= {f["ctdl_property"] for tree in p.golden.trees.values() for ents in tree.values() for e in ents
                      for f in e["fields"] if f.get("ctdl_property")}
        doc["not_scored"] = sorted({column(f["ctdl_property"]) for tree in p.golden.trees.values()
                                    for ents in tree.values() for e in ents for f in e["fields"]
                                    if f.get("ctdl_property") and f["ctdl_property"] not in props})
        for basis in BASES:
            whole, left_out = p.golden.trees[basis], p.golden.left_out.get(basis, [])
            pages = only_emitted(whole, props)
            sizes[basis] = sum(1 for ents in pages.values() for e in ents for f in e["fields"] if not is_implied(f))
            if not sizes[basis]:
                doc["results"][basis] = None  # nothing to score on this basis
                continue
            reports = run_scorer(p.records, pages, ctx.catalog, ctx.crawl, f"{p.golden.where} ({basis})")
            mine = value_rows(basis, pages, reports)
            doc["results"][basis] = result(pages, left_out, reports, mine)
            if pages != whole:  # xtra's own numbers, every column of the tree
                x = run_scorer(p.records, whole, ctx.catalog, ctx.crawl, f"{p.golden.where} ({basis})")["exact"]
                doc["results"][basis]["xtra"] = {"values": x["fields_total"],
                                                 "exact_match_rate": x["exact_match_rate"]}
            rows += mine
        doc["golden"]["values"] = sizes
        doc["columns"] = sorted({r["column"] for r in rows if r["basis"] == "rule"})
        ctx.write_table(f"{layout.score_dir(ctx.catalog, ctx.crawl, doc['id'])}/values.parquet", rows,
                        SCORE_VALUES, if_none_match=False)
        doc["status"] = "done"
        if doc["slot_names"]:
            doc["error"] = SLOT_NAMES
    except Exception as e:  # noqa: BLE001 - the score says why it failed
        doc["status"], doc["error"] = "failed", str(e)
        log(f"{doc['id']} failed: {e}")
    doc["finished_at"] = _now()
    _write(ctx, doc)
    return doc


def score(ctx: Ctx, golden: str | None, output: str | None = None, by: str = "", reason: str = "", log=print) -> dict:
    """Score an extract output against a golden dataset, now (the CLI); an existing score of the pair is returned."""
    p = prepare(ctx, golden, output, log)
    return existing(ctx, p) or finish(ctx, begin(ctx, p, by, reason), p, log)


def interrupt_running(ctx: Ctx) -> list[str]:
    """A score left `running` by a restart becomes `interrupted` (it can be scored again)."""
    out = []
    for doc in all_scores(ctx):
        if doc["status"] == "running":
            doc["status"], doc["finished_at"] = "interrupted", _now()
            _write(ctx, doc)
            out.append(doc["id"])
    return out


def pending(ctx: Ctx) -> dict | None:
    """scores/pending.json, when its time has come."""
    try:
        doc = ctx.root.read_json(layout.pending_score(ctx.catalog, ctx.crawl))
    except FileNotFoundError:
        return None
    return doc if doc.get("due_at", "") <= _now() else None


def done_pending(ctx: Ctx) -> None:
    try:
        ctx.root.delete(layout.pending_score(ctx.catalog, ctx.crawl))
    except FileNotFoundError:
        pass


# --- for the Evals tab -------------------------------------------------------------------------------
def goldens(ctx: Ctx) -> list[dict]:
    """What Evals can score against with Rule-matched: each golden dataset version, newest first, then the drafts
    (every extraction, `rs-NNNN`, scored as if it were published), newest first."""
    vs = golden_mod.versions(ctx)
    out = []
    for n in sorted(vs, reverse=True):
        try:
            pub = ctx.read_json(f"{vs[n]['path']}/publication.json", immutable=False)
        except FileNotFoundError:
            pub = {}
        out.append({"id": golden_mod.version_name(n), "kind": "version", "ruleset_version": n,
                    "published_at": pub.get("published_at"), "latest": n == max(vs)})
    for e in sorted(ctx.extractions(), key=lambda e: e["extraction"], reverse=True):
        out.append({"id": e["extraction"], "kind": "draft", "ruleset_version": e["ruleset_version"],
                    "published_at": None, "latest": False})
    return out


def _lineage(ctx: Ctx, doc: dict) -> list[dict]:
    """The lineage of the golden dataset a score read: its version's (for `human-reviewed`, the version it read),
    or a draft's, planned from its extraction."""
    g = doc["golden"]
    m = golden_mod.VERSION.search(g["id"]) or golden_mod.VERSION.search(g.get("from", "").rstrip("/"))
    if m:
        v = golden_mod.versions(ctx).get(int(m.group(1)))
        return ctx.rows(f"{v['path']}/lineage.parquet") if v else []
    if g["kind"] == "draft":
        from .review import LOADER

        return golden_mod.plan(LOADER.review(ctx, g["id"]))["lineage"]
    return []


def studio_targets(ctx: Ctx, doc: dict, rows: list[dict]) -> None:
    """Each scored value's Studio match, through the golden dataset's lineage: `rule_id`, `occurrence_key` and
    `value_index` (the match's), so a note or a verdict on a row in Evals lands on the row the Rules tab shows. A
    course listed twice on a page with the same golden_record_id has one lineage row per listing: the scored values
    take them in order (each tree keeps its records in page order). Values with no lineage get None."""
    by: dict[tuple, list[dict]] = defaultdict(list)
    for r in sorted(_lineage(ctx, doc), key=lambda r: r["value_index"] or 0):
        by[(r["page_stem"], r["golden_record_id"], r["ctdl_property"])].append(r)
    seen: Counter = Counter()
    for r in rows:
        k = (r["page_stem"], r["golden_record_id"], r["ctdl_property"])
        cands = by.get(k, [])
        i = seen[(r["basis"], *k)]
        seen[(r["basis"], *k)] += 1
        hit = cands[min(i, len(cands) - 1)] if cands else None
        r["rule_id"] = hit and hit["rule_id"]
        r["occurrence_key"] = hit and hit["occurrence_key"]
        r["value_index"] = hit and hit["match_value_index"]


def subject(golden_record_id: str | None) -> str | None:
    """A course code's subject, for Group by: its leading letters (NS912L → NS)."""
    m = re.match(r"[A-Za-z]+", golden_record_id or "")
    return m.group(0).upper() if m else None


# --- Where it's wrong (sme-fixes spec §8.4) ------------------------------------------------------------------------
#: How "Where it's wrong" groups the units that aren't a match, besides outcome × field: `auto` (the description label
#: for objects; the word diff for a paired value; the value shape for the rest), or one key for all.
WRONG_KEYS = ("auto", "label", "shape", "diff", "subject")
WRONG_EXAMPLES = 12  # courses linked per group


def _object(text: str | None) -> dict | None:
    if not text or not text.startswith("{"):
        return None
    try:
        v = json.loads(text)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _label(r: dict) -> str | None:
    """An object's description label (golden's, else the extracted one's)."""
    for text in (r.get("golden_value"), r.get("extracted_value")):
        obj = _object(text)
        if obj:
            v = obj.get("ceterms:description")
            if v is None and obj:
                v = next(iter(obj.values()))
            return str(v)
    return None


def _field_values(r: dict) -> tuple[str | None, str | None]:
    """The two sides of a row's (worst) differing field, else of its value."""
    g, x = _object(r.get("golden_value")), _object(r.get("extracted_value"))
    name = (r.get("field") or "").split(",")[0]
    if g is not None and name:
        k = next((k for k in g if _short(k) == name), None)
        if k:
            got = (x or {}).get(k)
            return str(g[k]), None if got is None else str(got)
    return r.get("golden_value"), r.get("extracted_value")


def _shape(v: str | None) -> str:
    from .strata import shape

    return shape(v) or "(empty)" if v is not None else "nothing"


def wrong_key(r: dict, key: str = "auto") -> tuple[str, str]:
    """(what it's grouped by, the group's key) for one unit that isn't a match."""
    if key == "subject":
        return "course subject", r.get("subject") or subject(r.get("golden_record_id")) or "—"
    if key == "diff" or (key == "auto" and r["outcome"] in ("wrong", "partial") and r.get("unit") != "object"):
        return "word diff", r.get("reason") or "—"
    if key == "label" or (key == "auto" and r.get("unit") == "object"):
        label = _label(r)
        if label is not None:
            if key == "auto" and r["outcome"] in ("wrong", "partial"):
                g, x = _field_values(r)
                return "value shape", f"{_shape(g)} → {_shape(x)}"
            return "description label", label
    if r["outcome"] in ("wrong", "partial"):
        g, x = _field_values(r)
        return "value shape", f"{_shape(g)} → {_shape(x)}"
    if r.get("unit") == "absent" or r["outcome"] == "unsure":
        return "reason", r.get("reason") or "—"
    v = r.get("golden_value") if r.get("golden_value") is not None else r.get("extracted_value")
    return "value shape", _shape(v)


def wrong_groups(rows: list[dict], key: str = "auto") -> list[dict]:
    """Every unit that isn't a match, grouped by outcome × field (objects) × a grouping key, biggest group first.
    Each group: its count, its courses, one example (golden → extracted, the row's key) and the Studio rows of its
    first courses (`targets`: rule_id, occurrence_key, golden_record_id), which open in the Rules tab."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r["outcome"] == "match":
            continue
        by, k = wrong_key(r, key)
        groups[(r["outcome"], r.get("field") or "", r["column"], by, k)].append(r)
    out = []
    for (outcome, field_, col, by, k), rs in groups.items():
        courses: dict[str, dict] = {}
        for r in rs:
            courses.setdefault(r.get("golden_record_id") or r["page_stem"], r)
        ex = rs[0]
        out.append({"outcome": outcome, "field": field_ or None, "column": col, "by": by, "key": k,
                    "reason": ex.get("reason"), "units": len(rs), "courses": len(courses),
                    "example": {"row": ex.get("key"), "golden_record_id": ex.get("golden_record_id"),
                                "golden_value": ex.get("golden_value"), "extracted_value": ex.get("extracted_value"),
                                "rule_id": ex.get("rule_id"), "occurrence_key": ex.get("occurrence_key")},
                    "targets": [{"golden_record_id": cid, "rule_id": r.get("rule_id"),
                                 "occurrence_key": r.get("occurrence_key")}
                                for cid, r in list(courses.items())[:WRONG_EXAMPLES]]})
    order = {o: i for i, o in enumerate(OUTCOMES)}
    return sorted(out, key=lambda g: (-g["units"], order.get(g["outcome"], 9), g["column"], g["key"]))


def scored_against(ctx: Ctx, output_id: str, golden_id: str) -> bool:
    """Whether a score of this extract output against this golden dataset exists (in any state: a failed one isn't
    retried by itself). Reads score.json files newest first, so it usually reads one."""
    for sid in reversed(score_ids(ctx)):
        doc = read(ctx, sid)
        if doc["output"]["id"] == output_id and doc["golden"]["id"] == golden_id:
            return True
    return False


# --- CLI ---------------------------------------------------------------------------------------------
def _line(name: str, r: dict | None) -> str:
    if not r:
        return f"  {name:<15} no values to score"
    o = r["outcomes"]
    rate = "n/a" if r["exact_match_rate"] is None else f"{r['exact_match_rate']:.1%}"
    line = (f"  {name:<15} {rate} exact of {r['values']:,} values · match {o['match']:,} · partial {o['partial']:,} "
            f"· wrong {o['wrong']:,} · missing {o['missing']:,}")
    if "extra" in o:  # a score from before sme-fixes has no extra, unsure, found or right
        pct = lambda x: "n/a" if x is None else f"{x:.1%}"  # noqa: E731
        line += (f" · unsure {o.get('unsure', 0):,} · extra {o['extra']:,}\n  {'':<15} found (recall) "
                 f"{pct(r.get('found'))} · right (precision) {pct(r.get('right'))} of {r.get('extracted', 0):,} "
                 f"candidates")
    return line


def cmd_score(args) -> int:
    ctx = Ctx.from_args(args)
    golden = HUMAN_REVIEWED if args.human_reviewed else args.draft or (
        golden_mod.version_name(args.ruleset) if args.ruleset else None)
    doc = score(ctx, golden, args.output, by=args.by, reason="golden-datasets score")
    out = doc["output"]
    print(f"{doc['id']}: extract output {out['id']} ({out['records']:,} records) vs {doc['golden']['id']} "
          f"[{doc['status']}]")
    if doc["status"] == "failed":
        print(f"  failed: {doc['error']}")
        return 1
    print(_line("human-reviewed", doc["results"].get("human")))
    print(_line("rule-matched", doc["results"].get("rule")))
    if out.get("records_mismatch"):
        print(f"  warning: {out['records']:,} records in the folder, the report says {out['records_written']:,}")
    if doc.get("slot_names"):
        print(f"  warning: {SLOT_NAMES}")
    return 0


# --- the home page's catalogs table (Evals spec §6.1, §6.2) ------------------------------------------------------
def column_key(label: str, path: str | None) -> str:
    """A home-table column: the CTDL path without prefixes, or the label for a property with no CTDL term."""
    return column(path) if path else label


#: Every property's column, in the fixed order (property-rules spec §4.9); the home table puts the other properties
#: in the Rules tab's order (columns_in_order).
STUDIO_COLUMNS = [column_key(label, t) for label, t in model.PROPERTIES]
COLUMN_LABELS = {column_key(label, t): (column(t).replace(">", " → ") if t else label) for label, t in model.PROPERTIES}
REQUIRED_COLUMNS = [column_key(r["label"], r["path"] or None) for r in model.PROPERTY_ROWS if r["required"]]


def columns_in_order(counts: Counter) -> list[str]:
    """Required columns first, then the others by values experts reviewed across catalogs (`counts`, by rule id),
    then sheet order: the Rules tab's order (§4.8)."""
    rest = [r for r in model.PROPERTY_ROWS if not r["required"]]
    rest.sort(key=lambda r: (-counts.get(r["rule_id"], 0), r["sheet_row"]))
    return REQUIRED_COLUMNS + [column_key(r["label"], r["path"] or None) for r in rest]


def column_statuses(ctx: Ctx, cache: dict | None = None) -> dict[str, dict]:
    """column → {status, ruleset, human, rule, found, no_rule}: `published` (in the latest golden dataset; `ruleset`
    names it), `needs work` (known wrong values: values its rule finds are marked wrong), or `in review`; `human` /
    `rule`: the column's values in the latest golden dataset as publishing writes it now (an expert reviewed them / its
    approved rule labels them; 0 while the column isn't published), `found`: the values its rules found in the latest
    extraction; `no_rule`: the property has no rule in this catalog yet (shown "—"). From the rules, the annotation
    log and golden.plan.

    `cache` keeps the result until the log moves, a new extraction or publication lands, or a role changes. The key is
    worked out without loading an extraction, so a warm home page loads none; a cold one loads each catalog's latest
    extraction without its parent (statuses don't use it), and the snapshot cache lets them go again."""
    from .review import LOADER

    vs = golden_mod.versions(ctx)
    doc: dict = {}
    if vs:
        try:
            doc = ctx.read_json(f"{vs[max(vs)]['path']}/publication.json", immutable=False)
        except FileNotFoundError:
            pass
    log = LOADER.log(ctx)
    log.events()  # reads what was appended since, so the offset is current
    key = ("column-statuses", ctx.catalog, ctx.crawl, ctx.latest_extraction(), doc.get("publication"),
           doc.get("published_at"), log.offset, LOADER.generation)
    if cache is not None and key in cache:
        return cache[key]
    published = set(doc.get("properties") or [])
    rv = LOADER.review(ctx, with_parent=False)
    counts = _column_counts(ctx, rv, doc)
    out = {}
    for r in golden_mod.property_rules(rv):
        c = counts.get(r["property"], {})
        n = {"human": c.get("human", 0), "rule": c.get("rule", 0), "found": c.get("found", 0)}
        k = column_key(r["property"], r["ctdl_property"])
        no_rule = rv.snap.rules[r["rule_id"]]["definition"].get("rule_type") == "none"
        if r["property"] in published:
            out[k] = {"status": "published", "ruleset": max(vs), **n, "no_rule": no_rule}
        else:
            out[k] = {"status": "needs work" if r["status"] == "needs work" else "in review", "ruleset": None,
                      **n, "no_rule": no_rule}
    if cache is not None:
        for old in [k for k in cache if isinstance(k, tuple) and k[:3] == key[:3]]:  # this catalog's older counts
            del cache[old]
        cache[key] = out
    return out


def coverage(columns: dict[str, dict]) -> int:
    """Properties with a rule in this catalog (§4.9)."""
    return sum(1 for k, c in columns.items() if k in COLUMN_LABELS and not c.get("no_rule"))


def _column_counts(ctx: Ctx, rv, doc: dict) -> dict[str, Counter]:
    """property → Counter(human, rule, found): the latest golden dataset's values as golden.plan writes them (on
    its publication's extraction, its properties), and the values the latest extraction's rules found (each item
    of a list counts)."""
    from .review import LOADER

    pub_rv = LOADER.review(ctx, doc["extraction"], with_parent=False) \
        if doc.get("extraction") and doc["extraction"] != rv.snap.ext else rv
    out: dict[str, Counter] = {}
    for row in golden_mod.plan(pub_rv, set(doc.get("properties") or []))["lineage"]:
        out.setdefault(row["property"], Counter())[row["approval"]] += 1
    for rid, r in rv.snap.rules.items():
        if r["kind"] == "property" and r.get("property_label"):
            out.setdefault(r["property_label"], Counter())["found"] += rv.snap.values(rid)
    return out


def latest_score(ctx: Ctx, basis: str, cache: dict | None = None) -> dict | None:
    """The newest finished score of xtra's latest extract output against the latest golden dataset, on one basis
    (human: the human-reviewed values, scored as `human-reviewed` or as the latest version; rule: the latest version's
    rule-matched values). None if there's no such score yet. Only score.json files are read (newest first); done ones
    are kept in `cache`."""
    outs, latest = outputs(ctx), latest_golden(ctx)
    if not outs or not latest:
        return None
    want = {HUMAN_REVIEWED, latest} if basis == "human" else {latest}
    for sid in reversed(score_ids(ctx)):
        key = ("score.json", ctx.catalog, ctx.crawl, sid)
        doc = (cache or {}).get(key) or read(ctx, sid)
        if doc["status"] == "done" and cache is not None:
            cache[key] = doc
        res = (doc.get("results") or {}).get(basis)
        if doc["status"] == "done" and res and doc["output"]["id"] == outs[-1]["id"] and doc["golden"]["id"] in want:
            return {"id": doc["id"], "golden": doc["golden"]["id"], "output": doc["output"]["id"],
                    "output_at": doc["output"].get("last_modified"), "values": res["values"],
                    "outcomes": res["outcomes"], "by_column": res.get("by_column") or {},
                    "implied": sorted(res.get("implied") or {})}
    return None
