"""What the golden dataset publishes for one property on one course, reviewer's answers included (sme-fixes §5.4, §6,
§7). `golden.plan` asks `fields(...)` for each (rule, course) and writes what it yields.

Per row, in this order:
1. **The reviewer's answer** (§7): the row's latest verdict is ✕ with an expected value and the rule still doesn't give
   it (state wrong / still wrong): the expected text is published instead of the rule's value, `approval: human`,
   `approved_by` the reviewer. The text is the `in` segments joined in page order, minus the `out` segments (a
   segment with no `polarity` is `in`). This applies to rows where the rule found nothing too.
2. **Absent** (§6): `{"ctdl_property", "property", "value": null, "absent": true, …}` when the rule claims "not on the
   page" (status `absent`; approved like any value: an expert's ✓ or the rule's approval), when a reviewer ✓'d a row
   where the rule found nothing (`no_match` / `empty`: they checked, it isn't on the page), or when a reviewer ✕'d it
   with the reason `not_on_page`. The last two are the reviewer's answers: `approval: human`, `approved_by` them.
3. Otherwise **the rule's values**, as before. A list of objects (§5.4) publishes one field per object, `value` the
   object (`{"ceterms:description": "…", "ceterms:timeRequired": "…"}`, page words) and `location` one location per
   object field; objects a reviewer ✕'d are left out, and objects a reviewer added (`expected.objects[]` on a `missing`
   item verdict the rule still doesn't give) are added, `approval: human`.
"""

from __future__ import annotations

from collections.abc import Iterator

from . import profiles_rule
from .review import Review, RowState, norm

NO_VALUE = ("no_match", "empty")


def fields(rule: dict, matches: list[dict], st: RowState | None, occ_css_path: str, human: dict, rule_ok: dict,
           column: bool) -> Iterator[dict]:
    """The golden values of one rule on one course: dicts {value, location, absent?, approval, approved_by,
    approved_at, match_value_index}. `human` maps a match's value_index to the expert verdict that makes it
    human-reviewed; `rule_ok` is the rule's approval; `column`: the property is being published (else only
    human-reviewed values are)."""
    answer = reviewer_answer(rule, st)
    if answer is not None:
        yield answer
        return
    status = matches[0]["status"] if matches else "none"
    if status == "absent":
        yield from absent_claim(matches[0], st, human, rule_ok, column)
        return
    if status in NO_VALUE and confirmed_nothing(st):
        yield {"value": None, "absent": True, "location": None, **_by(st.verdict), "match_value_index": None}
        return
    yield from rule_values(rule, matches, st, occ_css_path, human, rule_ok, column)
    if profiles_rule.is_profile(rule["definition"]) and st is not None:
        yield from added_objects(st)


def wants_row(st: RowState | None) -> bool:
    """A row whose rule found nothing that still publishes something: a reviewer's ✕ with an answer or a reason, or a
    ✓ on "nothing found"."""
    v = st.verdict if st is not None else None
    if v is None or v.get("type") != "verdict":
        return False
    if v.get("verdict") == "wrong":
        return bool(v.get("reasons")) or bool(answer_text(v.get("expected")))
    return v.get("verdict") == "correct"


def states_by_occurrence(rv: Review, rule_id: str) -> dict[str, RowState]:
    """Row states of a property rule keyed by occurrence key (its rows' keys)."""
    rows = rv.snap.rows(rule_id)
    states = rv.row_states(rule_id, rows)
    return {r["occurrence_key"]: states[r["key"]] for r in rows if r.get("occurrence_key")}


# --- 1. The reviewer's answer --------------------------------------------------------------------------------


def reviewer_answer(rule: dict, st: RowState | None) -> dict | None:
    v = st.verdict if st is not None else None
    if v is None or v.get("verdict") != "wrong" or rule["definition"].get("multiple"):
        return None
    if "not_on_page" in (v.get("reasons") or []):
        return {"value": None, "absent": True, "location": None, **_by(v), "match_value_index": None}
    text = answer_text(v.get("expected"))
    if text and st.state in ("wrong", "still-wrong"):
        return {"value": text, "location": _location(v["expected"]), **_by(v), "match_value_index": None}
    return None


def answer_text(expected: dict | None) -> str | None:
    """A ✕'s expected answer as one text: its `in` segments (page order, as saved) joined by line breaks, with any
    `out` segment cut out of the `in` segment it lies in."""
    if not expected:
        return None
    segs = _segments(expected)
    outs = [s for s in segs if s.get("polarity") == "out"]
    if not outs:
        text = expected.get("text")
        return text.strip() if text and text.strip() else None
    ins = [s for s in segs if s.get("polarity", "in") != "out"]
    pieces = [piece for s in ins if (piece := cut_out(s, outs))]
    return "\n".join(pieces) or None


def cut_out(segment: dict, outs: list[dict]) -> str:
    text = segment.get("text") or ""
    cuts = cuts_inside(segment, text, outs)
    return norm(remove_spans(text, cuts)) if cuts else text.strip()


def cuts_inside(segment: dict, text: str, outs: list[dict]) -> list[tuple[int, int]]:
    a = segment.get("char_start")
    return sorted((o["char_start"] - a, o["char_end"] - a) for o in outs
                  if a is not None and o.get("css_path") == segment.get("css_path") and o.get("char_start") is not None
                  and o["char_start"] >= a and o["char_end"] <= a + len(text))


def remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    kept, at = [], 0
    for x, y in spans:
        kept.append(text[at:x])
        at = max(at, y)
    kept.append(text[at:])
    return "".join(kept)


def _location(e: dict) -> dict | None:
    s = next((x for x in _segments(e) if x.get("polarity", "in") != "out"), None)
    if not s or not s.get("css_path"):
        return None
    return {"css_path": s["css_path"], "char_start": s.get("char_start"), "char_end": s.get("char_end")}


def _segments(expected: dict) -> list[dict]:
    segs = expected.get("segments") or []
    return segs if segs else [expected]


# --- 2. Absent -----------------------------------------------------------------------------------------------


def absent_claim(first: dict, st: RowState | None, human: dict, rule_ok: dict, column: bool) -> Iterator[dict]:
    v = st.verdict if st is not None else None
    if v is not None and v.get("verdict") == "wrong":
        return  # ✕ on the claim: it is on the page, and no answer was selected
    x = human.get(0)
    if x is not None or column:
        yield {"value": None, "absent": True, "location": _loc(first),
               **(_by(x) if x is not None else rule_ok), "match_value_index": 0}


def confirmed_nothing(st: RowState | None) -> bool:
    v = st.verdict if st is not None else None
    return v is not None and v.get("verdict") == "correct" and st.state == "correct"


# --- 3. The rule's values ------------------------------------------------------------------------------------


def rule_values(rule: dict, matches: list[dict], st: RowState | None, occ_css_path: str, human: dict, rule_ok: dict,
                column: bool) -> Iterator[dict]:
    profile = profiles_rule.is_profile(rule["definition"])
    for m in matches:
        if m["status"] != "found" or rejected_object(m, st, profile):
            continue
        x = human.get(m["value_index"])
        if x is None and not column:
            continue
        yield match_field(m, profile, occ_css_path, _by(x) if x is not None else rule_ok)


def rejected_object(m: dict, st: RowState | None, profile: bool) -> bool:
    """A reviewer said this object isn't part of the answer."""
    if not profile or st is None:
        return False
    item = st.items.get(norm(m["value"]))
    return item is not None and item.state == "wrong"


def match_field(m: dict, profile: bool, occ_css_path: str, ok: dict) -> dict:
    obj = profiles_rule.parse(m["value"]) if profile else None
    if obj is None:
        return {"value": m["value"], "location": _loc(m), **ok, "match_value_index": m["value_index"]}
    locs = profiles_rule.item_fields(m, occ_css_path) or {}
    return {"value": obj, "location": field_locations(locs) or _loc(m), **ok, "match_value_index": m["value_index"]}


def added_objects(st: RowState) -> Iterator[dict]:
    """Objects a reviewer added that the rule still doesn't give."""
    for e in st.missing_items:
        for o in (e.get("expected") or {}).get("objects") or []:
            fs = dict(sorted((o.get("fields") or {}).items()))
            obj = {k: f.get("text") for k, f in fs.items() if f.get("text")}
            if obj:
                yield {"value": obj, "location": field_locations(fs), **_by(e), "match_value_index": None}


def field_locations(fields_by_name: dict) -> dict:
    return {k: {"css_path": f.get("css_path"), "char_start": f.get("char_start"), "char_end": f.get("char_end")}
            for k, f in fields_by_name.items()}


def _by(e: dict) -> dict:
    return {"approval": "human", "approved_by": e["author"], "approved_at": e["at"]}


def _loc(m: dict) -> dict | None:
    return ({"css_path": m["full_css_path"], "char_start": m["char_start"], "char_end": m["char_end"]}
            if m.get("css_path") is not None else None)
