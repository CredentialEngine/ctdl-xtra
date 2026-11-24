"""Findings, property status and discussion (LearningProgram spec wave 4, §1 and §4; plan Phase 6): the running notes'
per-property sections, kept as data. Each is per class and property, across catalogs:

    properties/<class>/<property>/findings.jsonl   append-only: each save of a finding is its whole record (latest wins)
    properties/<class>/<property>/status.json      Needs review / Done, who set it and when, and the earlier ones
    properties/<class>/<property>/threads.jsonl    comments on a finding or a Where-it's-wrong group, in the comment
                                                   event shape the Rules tab's annotations use (a comment on one unit
                                                   goes to the catalog's own annotations, as Evals already does)

A finding has Seth's fields (code, title, kind, whose error, cause, fix, assessment), its state (open or fixed: a
person says fixed, even at 0 units, §4.3) and the Where-it's-wrong groups it covers (`links`: catalog, outcome, field,
how they were grouped and the group's key), whose units are counted live from each catalog's latest score. A finding
imported from the running notes keeps the notes' counts (`counts`, `catalogs`) until it is linked to groups.

Who can do what (§4.1): anyone can set Needs review; only the SME role sets Done.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from . import classes
from .errors import UserError
from .log import new_id
from .storage import Root

STATUSES = ("needs review", "done")
KINDS = ("mismatch", "missing")
WHOSE = ("silver", "extractor", "baseline", "normalization")
STATES = ("open", "fixed")
FIELDS = ("code", "title", "kind", "whose", "cause", "fix", "assessment")
#: the outcomes a finding's counts are kept for, each as golden / silver units
COUNTED = ("partial", "wrong", "missing")


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def folder(cls: str, column: str) -> str:
    """A property's folder: `properties/course/description`, `properties/course/creditValue_minValue`."""
    return f"properties/{classes.get(cls).slug}/{re.sub(r'[^A-Za-z0-9_-]+', '_', column).strip('_')}"


def _lines(root: Root, path: str) -> list[dict]:
    try:
        data = root.read_bytes(path)
    except FileNotFoundError:
        return []
    return [json.loads(x) for x in data.decode().splitlines() if x.strip()]


def _append(root: Root, path: str, doc: dict) -> None:
    root.append(path, (json.dumps(doc, ensure_ascii=False) + "\n").encode())


# --- status -----------------------------------------------------------------------------------------------------
def status(root: Root, cls: str, column: str) -> dict | None:
    try:
        return root.read_json(f"{folder(cls, column)}/status.json")
    except FileNotFoundError:
        return None


def set_status(root: Root, cls: str, column: str, value: str, author: str, role: str | None) -> dict:
    """Needs review (anyone) or Done (the SME role only). The earlier ones are kept under `history`."""
    if value not in STATUSES:
        raise UserError(f"status must be one of {', '.join(STATUSES)}")
    if not author:
        raise UserError("say who sets it")
    if value == "done" and role != "sme":
        raise PermissionError("only a subject-matter expert can set Done")
    old = status(root, cls, column)
    doc = {"status": value, "by": author, "role": role, "at": now(),
           "history": [*(old or {}).get("history", []), *([{k: old[k] for k in ("status", "by", "role", "at")}]
                                                         if old else [])]}
    root.write_json(f"{folder(cls, column)}/status.json", doc)
    return doc


def statuses(root: Root, cls: str) -> dict[str, dict]:
    """column → its status, for every property of the class that has one (the score views' rows)."""
    from . import model, scores

    out = {}
    for label, term in model.properties_of(cls):
        col = scores.column_key(label, term)
        s = status(root, cls, col)
        if s:
            out[col] = {k: s[k] for k in ("status", "by", "at")}
    return out


# --- findings ---------------------------------------------------------------------------------------------------
def findings(root: Root, cls: str, column: str) -> list[dict]:
    """The property's findings, each its latest save, in code order (D1, D1b, D2 … D10, then M1 …)."""
    latest: dict[str, dict] = {}
    for doc in _lines(root, f"{folder(cls, column)}/findings.jsonl"):
        first = latest.get(doc["id"], {}).get("created")
        latest[doc["id"]] = {**doc, "created": first or {"at": doc["at"], "by": doc["author"]}}

    def order(f: dict):
        m = re.match(r"([A-Za-z]*)(\d*)(.*)", f.get("code") or "")
        return (m.group(1), int(m.group(2) or 0), m.group(3), f["created"]["at"])
    return sorted(latest.values(), key=order)


def save_finding(root: Root, cls: str, column: str, author: str, data: dict, finding_id: str | None = None) -> dict:
    """Create a finding, or save a new version of one: its fields, state and links. Returns the saved record."""
    if not author:
        raise UserError("say who saves it")
    old = next((f for f in findings(root, cls, column) if f["id"] == finding_id), None) if finding_id else None
    if finding_id and old is None:
        raise KeyError(finding_id)
    doc = {k: v for k, v in (old or {}).items() if k != "created"}
    for k in (*FIELDS, "state", "links", "counts", "catalogs", "source"):
        if k in data:
            doc[k] = data[k]
    doc.setdefault("state", "open")
    doc.setdefault("kind", "mismatch")
    doc.setdefault("links", [])
    if not (doc.get("code") or "").strip() or not (doc.get("title") or "").strip():
        raise UserError("a finding needs a code and a title")
    if doc["kind"] not in KINDS:
        raise UserError(f"kind must be one of {', '.join(KINDS)}")
    if doc.get("whose") not in (None, "", *WHOSE):
        raise UserError(f"whose error must be one of {', '.join(WHOSE)}")
    if doc["state"] not in STATES:
        raise UserError(f"state must be one of {', '.join(STATES)}")
    if any(f["code"] == doc["code"] and f["id"] != finding_id for f in findings(root, cls, column)):
        raise UserError(f"{doc['code']} is already a finding on this property")
    doc.update(id=finding_id or new_id("fd"), at=now(), author=author)
    _append(root, f"{folder(cls, column)}/findings.jsonl", doc)
    return next(f for f in findings(root, cls, column) if f["id"] == doc["id"])


def link_key(link: dict) -> tuple:
    """A Where-it's-wrong group, as a finding links it: its catalog, outcome, field, grouping and key."""
    return (link.get("catalog"), link.get("outcome"), link.get("field") or None, link.get("by"), link.get("key"))


# --- threads ----------------------------------------------------------------------------------------------------
def comments(root: Root, cls: str, column: str) -> list[dict]:
    return _lines(root, f"{folder(cls, column)}/threads.jsonl")


def add_comment(root: Root, cls: str, column: str, author: str, note: str, target: dict) -> dict:
    """A comment on a finding (`{kind: finding, id}`) or a group (`{kind: group, catalog, outcome, field, by, key}`)."""
    if not author or not (note or "").strip():
        raise UserError("a comment needs an author and a note")
    if target.get("kind") == "finding":
        if not any(f["id"] == target.get("id") for f in findings(root, cls, column)):
            raise KeyError(target.get("id"))
    elif target.get("kind") != "group" or not target.get("catalog"):
        raise UserError("a comment is on a finding or on a group of a catalog")
    ev = {"annotation_id": new_id("an"), "type": "comment", "at": now(), "author": author, "note": note.strip(),
          "target": {k: target.get(k) for k in ("kind", "id", "catalog", "outcome", "field", "by", "key")
                     if target.get(k) is not None}}
    _append(root, f"{folder(cls, column)}/threads.jsonl", ev)
    return ev


def thread_key(target: dict) -> str:
    """One thread's key: `finding:<id>`, or `group:<catalog>|<outcome>|<field>|<by>|<key>`."""
    if target.get("kind") == "finding":
        return f"finding:{target.get('id')}"
    return "group:" + "|".join(str(x or "") for x in link_key(target))


# --- the running notes' codes -----------------------------------------------------------------------------------
def seed(root: Root, cls: str, column: str, codes: list[dict], author: str = "Seth Alt") -> list[str]:
    """Import findings (the running notes' codes, verbatim) a property doesn't have yet; returns the codes added."""
    have = {f["code"] for f in findings(root, cls, column)}
    added = []
    for c in codes:
        if c["code"] in have:
            continue
        save_finding(root, cls, column, c.get("author") or author, {**c, "source": "running notes, 2026-11-18"})
        added.append(c["code"])
    return added


# --- CLI --------------------------------------------------------------------------------------------------------
NOTES = __file__.rsplit("/", 1)[0] + "/data/running_notes_description.json"


def cmd_seed(args) -> int:
    from .storage import open_root

    doc = json.loads(open(args.file or NOTES, encoding="utf-8").read())
    if classes.get(doc["class"]).slug != args.cls:
        raise UserError(f"{args.file or NOTES} is for {doc['class']}, not {args.cls}")
    added = seed(open_root(args.root), args.cls, doc["column"], doc["findings"])
    print(f"{doc['column']}: {len(added)} finding{'' if len(added) == 1 else 's'} added"
          + (f" ({', '.join(added)})" if added else ", every code was there already"))
    return 0


def cmd_list(args) -> int:
    from .storage import open_root

    root = open_root(args.root)
    s = status(root, args.cls, args.property)
    print(f"{args.property}: {s['status']} (set by {s['by']}, {s['at']})" if s else f"{args.property}: no status yet")
    for f in findings(root, args.cls, args.property):
        n = ", ".join(f"{o} {c[0]} / {c[1]}" for o, c in (f.get("counts") or {}).items() if c)
        print(f"  {f['code']:<4} {f['state']:<5} {f.get('whose') or '-':<13} {f['title']}" + (f"  [{n}]" if n else ""))
    return 0
