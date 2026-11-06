"""The whole golden suite (one-rule-runs spec §3.3): every `rule try` and `rule publish` checks **all** of a catalog's
rules against **all** their golden values, and a publish is refused when anything that was right got worse.

Golden values, per property rule:
- the latest ✓ on a value: the value marked correct (`value_seen`);
- the latest ✕ with an expected value: that value;
- values Claude inferred in this run (`inferred.json`, {rule, course, annotation, value}): for a ✕ with no
  expected value, the value Claude worked out from the page and the notes.

A golden value *matches* when the rule's value on that course equals it (whitespace collapsed, as everywhere).
Regression = a golden value that matched before no longer matches, or a rule matches fewer of its golden values than
before. Nothing else blocks; values with no verdict are counted as "values changed", per rule.
"""

from __future__ import annotations

from .review import Review, Snapshot, norm
from .scorecard import changed_rules, pair_rows

KIND_WORDS = {"correct": "marked correct, value changed", "expected": "expected value no longer produced",
              "inferred": "inferred value no longer produced"}


def _index(snap: Snapshot | None, rid: str) -> tuple[dict, dict]:
    if snap is None or rid not in snap.rules:
        return {}, {}
    rows = snap.rows(rid)
    return {r["key"]: r for r in rows}, {(r.get("course_key"), r["page_stem"]): r for r in rows if r.get("course_key")}


def _find(index: tuple[dict, dict], target: dict) -> dict | None:
    by_key, by_cp = index
    row = by_key.get(target.get("occurrence_key") or "")
    if row is None and target.get("course_key"):
        row = by_cp.get((target["course_key"], target.get("page_stem")))
    return row


def golden_values(rv: Review, rules: dict[str, dict], inferred: list[dict] | None = None) -> dict[str, list[dict]]:
    """rule → [{course, page_stem, occurrence_key, kind, want, annotation}]: the golden values of every property
    rule. `kind`: correct | expected | inferred."""
    out: dict[str, list[dict]] = {}
    extra: dict[tuple, dict] = {(i["rule"], i["annotation"]): i for i in inferred or []}
    for rid, r in rules.items():
        if r["kind"] != "property":
            continue
        got = []
        for e in rv.verdicts_for(rid)["latest"].values():
            t = e["target"]
            if t.get("kind") != "match":
                continue
            base = {"course": t.get("course_key"), "page_stem": t.get("page_stem"),
                    "occurrence_key": t.get("occurrence_key"), "annotation": e["annotation_id"]}
            exp = (e.get("expected") or {}).get("text")
            if e["verdict"] == "correct":
                got.append(base | {"kind": "correct", "want": t.get("value_seen")})
            elif e["verdict"] == "wrong" and exp is not None:
                got.append(base | {"kind": "expected", "want": exp})
            elif e["verdict"] == "wrong" and (rid, e["annotation_id"]) in extra:
                got.append(base | {"kind": "inferred", "want": extra[(rid, e["annotation_id"])]["value"]})
        if got:
            out[rid] = got
    return out


def values_changed(base: Snapshot | None, draft: Snapshot, rid: str, keep: int = 50) -> dict:
    """How many courses' values differ between the base version and the draft (changed, new or gone)."""
    a = base.rows(rid) if base is not None and rid in base.rules else []
    b = draft.rows(rid) if rid in draft.rules else []
    pairs, new, gone = pair_rows(a, b)
    moved = [y for x, y in pairs if norm(x["value"]) != norm(y["value"]) or x["status"] != y["status"]] + new + gone
    courses = sorted({r.get("course_key") or r["page_stem"] for r in moved})
    return {"count": len(moved), "of": len(b), "courses": courses[:keep]}


def score(base: Snapshot | None, draft: Snapshot, events: list[dict], inferred: list[dict] | None = None,
          drafted: list[str] | None = None) -> dict:
    """The whole suite: {rules, golden, now_right, inferred, got_worse, per_rule, regressions, changed}.

    `changed` = the rules whose definition changed (`drafted`) or whose values changed, each with its values_changed.
    """
    rv = Review(draft, events)
    gold = golden_values(rv, draft.rules, inferred)
    per_rule, regressions = {}, []
    now_right = n_inferred = 0
    for rid, values in gold.items():
        bi, di = _index(base, rid), _index(draft, rid)
        before = after = 0
        right, worse = [], []
        for g in values:
            want = norm(g["want"])
            was = _find(bi, g)
            now = _find(di, g)
            ok_before = base is not None and norm(was["value"] if was else None) == want
            ok_after = norm(now["value"] if now else None) == want
            before += ok_before
            after += ok_after
            who = g["course"] or g["page_stem"]
            if ok_after and not ok_before:
                right.append({"course": who, "kind": g["kind"]})
                now_right += 1
                n_inferred += g["kind"] == "inferred"
            elif ok_before and not ok_after:
                worse.append({"course": who, "kind": g["kind"], "annotation": g["annotation"]})
        per_rule[rid] = {"golden": len(values), "before": before, "after": after, "now_right": right, "got_worse": worse}
        for w in worse:
            regressions.append({"rule": rid, **w})
        if after < before and not worse:  # can't happen without a lost value, but the rule is the spec's
            regressions.append({"rule": rid, "course": None, "kind": "fewer", "annotation": None})
    moved = set(drafted or [])
    if base is not None:
        moved |= set(changed_rules(base, draft))
    changed = {rid: values_changed(base, draft, rid) for rid in sorted(moved) if rid in draft.rules or
               (base is not None and rid in base.rules)}
    return {"rules": len(draft.rules), "golden": sum(len(v) for v in gold.values()), "now_right": now_right,
            "inferred": n_inferred, "got_worse": len(regressions), "per_rule": per_rule,
            "regressions": regressions, "changed": changed}


def headline(s: dict) -> str:
    """The one line every try and publish prints first."""
    inf = f" ({s['inferred']} inferred)" if s["inferred"] else ""
    return (f"Whole suite: {s['rules']} rules, {s['golden']:,} golden values. "
            f"{s['now_right']} now right{inf}, {s['got_worse']} got worse.")


def checked_fact(s: dict) -> str:
    """The report's Checked fact (spec §1.4)."""
    worse = "Nothing that was right got worse." if not s["got_worse"] else \
        f"{s['got_worse']} that {'was' if s['got_worse'] == 1 else 'were'} right got worse."
    return f"All {s['rules']} rules against {s['golden']:,} golden values. {worse}"


def lines(s: dict, names: dict[str, str]) -> list[str]:
    """The headline, then detail only where something moved."""
    out = [headline(s)]
    if s["changed"]:
        out.append("Changed: " + ", ".join(
            f"{names.get(rid, rid)} ({c['count']:,} value{'' if c['count'] == 1 else 's'})"
            for rid, c in s["changed"].items()))
    for rid, r in s["per_rule"].items():
        bits = []
        if r["now_right"]:
            bits.append("now right " + ", ".join(x["course"] + (" (inferred)" if x["kind"] == "inferred" else "")
                                                 for x in r["now_right"]))
        if r["got_worse"]:
            bits.append("got worse " + ", ".join(f"{x['course']} ({KIND_WORDS[x['kind']]})" for x in r["got_worse"]))
        if bits:
            out.append(f"  {names.get(rid, rid)}: " + "; ".join(bits))
    return out
