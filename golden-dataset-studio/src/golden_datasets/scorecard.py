"""Is version B of a rule (or ruleset) better than A? The library behind Compare and `rule try` / `rule publish`
(spec §6 "The scorecard", §7.4, §5.8).

Rows of the two versions are joined on their key (occurrence_key, or page_stem for page rules), falling back to
(record_external_identifier, page) and then record_external_identifier alone; rows that can't be joined are "new" or "vanished" (D9).

Each annotated row gets an outcome, in this order (the query of spec §5.8):
- `unchanged`   the value is the same in A and B;
- `fixed`       it was marked wrong and B now gives the expected text;
- `newly wrong` it was marked correct and B changed it;
- `still wrong` it was marked wrong and B changed it, but not to the expected text.
Questions for the institution are left out.

Jared's earlier verdicts are listed in history-signal order (Eric's A4.1, spec §8): rows whose value changed since
they were marked correct first (`changed-since-correct`), then rows marked wrong (`previously-wrong`: still wrong,
then fixed), then the rows that didn't change; wrong before correct within each.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict

from .review import Review, Snapshot, norm

WORD = re.compile(r"\s+|[^\s]+")
#: Outcome → (history signal, order) for the earlier-verdicts list.
HISTORY = {"newly wrong": ("changed-since-correct", 0), "still wrong": ("previously-wrong", 1),
           "fixed": ("previously-wrong", 2), "unchanged": (None, 3)}


def compare(a: Snapshot, b: Snapshot, review: Review, rules: list[str] | None = None, *,
            signal_rows: int | None = None) -> dict:
    ids = rules if rules is not None else changed_rules(a, b)
    cards = [rule_scorecard(rid, a, b, review, signal_rows=signal_rows) for rid in ids]
    total = {k: sum(c["annotated"][k] for c in cards) for k in ("fixed", "still_wrong", "newly_wrong", "unchanged")}
    return {"a": a.ext, "b": b.ext, "a_ruleset": a.ruleset_version, "b_ruleset": b.ruleset_version,
            "records_changed": sum(records_changed(c) for c in cards),
            "values_changed": sum(c["values"]["changed"] for c in cards), "totals": total, "rules": cards}


def changed_rules(a: Snapshot, b: Snapshot) -> list[str]:
    """Rules whose version differs between A and B, plus rules whose values changed (e.g. under a changed
    locator), in display order."""
    from .model import KIND_ORDER

    out = [rid for rid in sorted(set(a.rules) | set(b.rules)) if rule_changed(a, b, rid)]
    return sorted(out, key=lambda r: (KIND_ORDER[(b.rules.get(r) or a.rules[r])["kind"]], r))


def rule_changed(a: Snapshot, b: Snapshot, rid: str) -> bool:
    ra, rb = a.rules.get(rid), b.rules.get(rid)
    if ra is None or rb is None or ra["content_hash"] != rb["content_hash"]:
        return True
    av = {r["key"]: (r["value"], r["status"]) for r in a.rows(rid)}
    bv = {r["key"]: (r["value"], r["status"]) for r in b.rows(rid)}
    return av != bv


def records_changed(card: dict) -> int:
    """Records whose value changed, appeared or vanished: the counts of Compare's left column."""
    v = card["values"]
    return v["changed"] + v["new"] + v["vanished"]


def format_card(card: dict, b_label: str = "draft") -> str:
    """The text `rule try` prints (spec §6)."""
    a = card["annotated"]
    v = card["values"]
    pct = f"{100 * v['changed'] / v['total']:.0f}%" if v["total"] else "–"
    sig = ", ".join(f"{s['signal']} {s['a']}→{s['b']}" for s in card["signals"]) or "none"
    head = f"{card['rule_id']}  v{card['a_version']} → {b_label}" if card["a_version"] else f"{card['rule_id']}  new → {b_label}"
    return "\n".join([
        head,
        f"  annotated rows {a['rows']:>6}   fixed {a['fixed']}, still wrong {a['still_wrong']}, "
        f"newly wrong {a['newly_wrong']}, unchanged {a['unchanged']}",
        f"  values changed {v['changed']:>6} of {v['total']} ({pct})   new {v['new']}, vanished {v['vanished']}",
        f"  signals        {sig}",
        f"  verdict        {card['verdict']}",
    ])


# --- One rule's scorecard ---------------------------------------------------------------------------------------


def rule_scorecard(rule_id: str, a: Snapshot | None, b: Snapshot, review: Review, sample: int = 12,
                   seed: str = "compare", signal_rows: int | None = None) -> dict:
    """Scorecard for one rule between snapshots A (None = the rule is new) and B.

    `signal_rows` caps each signal's lost / gained list (None = all); `lost_total` / `gained_total` give the full
    counts either way."""
    a_rows = a.rows(rule_id) if a is not None and rule_id in a.rules else []
    b_rows = b.rows(rule_id) if rule_id in b.rules else []
    pairs, new, vanished = pair_rows(a_rows, b_rows)
    changed = [(x, y) for x, y in pairs if norm(x["value"]) != norm(y["value"]) or x["status"] != y["status"]]
    annotated = annotated_rows(rule_id, review, pairs)
    tallies = annotated_counts(annotated)
    others = unannotated_changes(changed, annotated, seed)
    values = {"changed": len(changed), "total": len(b_rows), "new": len(new), "vanished": len(vanished)}
    return {**rule_header(rule_id, a, b), "annotated": tallies, "annotated_rows": annotated, "values": values,
            "signals": signal_changes(a_rows, b_rows, pairs, new, vanished, signal_rows),
            "sample": [_brief(x, y) for x, y in others[:sample]], "sample_total": len(others),
            "new_rows": [_brief(None, y) for y in new[:sample]],
            "vanished_rows": [_brief(x, None) for x in vanished[:sample]],
            "verdict": card_verdict(tallies, values), "key_map_size": len({y["key"] for _, y in pairs})}


def rule_header(rule_id: str, a: Snapshot | None, b: Snapshot) -> dict:
    rule_a = a.rules.get(rule_id) if a is not None else None
    rule_b = b.rules.get(rule_id)
    rule = rule_b or rule_a
    return {"rule_id": rule_id, "kind": rule["kind"], "ctdl_property": rule.get("ctdl_property"),
            "property_label": rule.get("property_label"),
            "a_version": rule_a["version"] if rule_a else None, "b_version": rule_b["version"] if rule_b else None,
            "why": (rule_b or {}).get("why", "")}


def card_verdict(tallies: dict, values: dict) -> str:
    fixed, newly, still = tallies["fixed"], tallies["newly_wrong"], tallies["still_wrong"]
    if newly:
        return "WORSE (newly wrong > 0)"
    if fixed and not still:
        return "BETTER (fixed > 0, newly wrong = 0)"
    if fixed:
        return "BETTER, NOT DONE (fixed > 0, still wrong > 0)"
    if not values["changed"] and not values["new"] and not values["vanished"]:
        return "SAME (no value changed)"
    return "UNKNOWN (no annotated row changed)"


def unannotated_changes(changed: list[tuple[dict, dict]], annotated: list[dict], seed: str) -> list[tuple[dict, dict]]:
    annotated_keys = {r["key"] for r in annotated}
    others = [(x, y) for x, y in changed if y["key"] not in annotated_keys]
    others.sort(key=lambda p: hashlib.sha1(f"{seed}:{p[1]['key']}".encode()).hexdigest())
    return others


# --- Annotated rows ---------------------------------------------------------------------------------------------


def annotated_rows(rule_id: str, review: Review, pairs: list[tuple[dict, dict]]) -> list[dict]:
    latest = review.verdicts_for(rule_id)["latest"]
    by_cp = {(e["target"].get("record_external_identifier"), e["target"].get("page_stem")): e for e in latest.values()
             if e["target"].get("record_external_identifier")}
    rows = []
    for x, y in pairs:
        e = latest.get(x["key"]) or latest.get(y["key"]) or by_cp.get((y.get("record_external_identifier"), y["page_stem"]))
        if e is not None and e["verdict"] in ("correct", "wrong"):
            rows.append(annotated_row(e, x, y))
    return sorted(rows, key=verdict_order)


def annotated_row(e: dict, x: dict, y: dict) -> dict:
    expected = (e.get("expected") or {}).get("text")
    oc = outcome(e["verdict"], x["value"], y["value"], expected)
    items = item_diff(x, y)
    return {"key": y["key"], "record_external_identifier": y.get("record_external_identifier"),
            "page_stem": y["page_stem"], "verdict": e["verdict"], "author": e["author"], "note": e.get("note"),
            "expected": expected, "a_value": x["value"], "b_value": y["value"], "outcome": oc,
            "diff": word_diff(x["value"], y["value"]), "css_path": y.get("css_path"),
            "char_start": y.get("char_start"), "char_end": y.get("char_end"),
            "annotation_id": e["annotation_id"], "history": history_signal(e["verdict"], oc),
            **({"items": items} if items else {})}


def annotated_counts(annotated: list[dict]) -> dict:
    counts = Counter(r["outcome"] for r in annotated)
    return {"rows": len(annotated), "fixed": counts["fixed"], "still_wrong": counts["still wrong"],
            "newly_wrong": counts["newly wrong"], "unchanged": counts["unchanged"]}


def outcome(verdict: str, a_value: str | None, b_value: str | None, expected: str | None) -> str:
    if norm(a_value) == norm(b_value):
        return "unchanged"
    if verdict == "wrong" and expected is not None and norm(b_value) == norm(expected):
        return "fixed"
    if verdict == "correct":
        return "newly wrong"
    return "still wrong"


def history_signal(verdict: str, oc: str) -> str:
    """The history signal (spec §8) an annotated row carries in this comparison."""
    sig = HISTORY[oc][0]
    if sig is None:
        return "previously-wrong" if verdict == "wrong" else "previously-correct"
    return sig


def verdict_order(r: dict) -> tuple:
    return (HISTORY[r["outcome"]][1], r["verdict"] != "wrong", r.get("record_external_identifier") or "", r["key"])


# --- Signals before → after -------------------------------------------------------------------------------------


def signal_changes(a_rows: list[dict], b_rows: list[dict], pairs: list[tuple[dict, dict]], new: list[dict],
                   vanished: list[dict], signal_rows: int | None) -> list[dict]:
    """Each signal's count in A and B, with the rows that lost (−) and gained (+) it."""
    sa = {x["key"]: _signal_names(x) for x in a_rows}
    sb = {y["key"]: _signal_names(y) for y in b_rows}
    count_a = Counter(name for names in sa.values() for name in names)
    count_b = Counter(name for names in sb.values() for name in names)
    lost, gained = signal_moves(sa, sb, pairs, new, vanished)

    def briefs(rows: list) -> list[dict]:
        return [_brief(x, y) for x, y in (rows if signal_rows is None else rows[:signal_rows])]

    return [{"signal": s, "a": count_a[s], "b": count_b[s],
             "lost": briefs(lost.get(s, [])), "gained": briefs(gained.get(s, [])),
             "lost_total": len(lost.get(s, [])), "gained_total": len(gained.get(s, []))}
            for s in sorted(set(count_a) | set(count_b), key=lambda s: (-(count_a[s] + count_b[s]), s))]


def signal_moves(sa: dict, sb: dict, pairs: list[tuple[dict, dict]], new: list[dict],
                 vanished: list[dict]) -> tuple[dict, dict]:
    """signal → [(row in A, row in B)] that lost it, and that gained it; rows new in B gain their signals, rows gone
    from A lose theirs."""
    lost, gained = defaultdict(list), defaultdict(list)
    for x, y in pairs:
        for name in sa.get(x["key"], set()) - sb.get(y["key"], set()):
            lost[name].append((x, y))
        for name in sb.get(y["key"], set()) - sa.get(x["key"], set()):
            gained[name].append((x, y))
    for y in new:
        for name in sb.get(y["key"], set()):
            gained[name].append((None, y))
    for x in vanished:
        for name in sa.get(x["key"], set()):
            lost[name].append((x, None))
    return lost, gained


def _signal_names(row: dict) -> set[str]:
    return {s["signal"] for s in row.get("signals", [])}


# --- Pairing rows and showing a change --------------------------------------------------------------------------


def pair_rows(a_rows: list[dict], b_rows: list[dict]) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """(pairs, new in B, vanished from A)."""
    index = _index(a_rows)
    pairs, new, used = [], [], set()
    for b in b_rows:
        a = partner(index, b)
        if a is None or a["key"] in used:
            new.append(b)
        else:
            used.add(a["key"])
            pairs.append((a, b))
    vanished = [a for a in a_rows if a["key"] not in used]
    return pairs, new, vanished


def partner(index: tuple[dict, dict, dict], b: dict) -> dict | None:
    """B's row in A: same key, else same record on the same page, else the record's only row."""
    a_key, a_cp, a_c = index
    a = a_key.get(b["key"])
    if a is None and b.get("record_external_identifier"):
        a = a_cp.get((b["record_external_identifier"], b["page_stem"]))
        if a is None and len(a_c.get(b["record_external_identifier"], [])) == 1:
            a = a_c[b["record_external_identifier"]][0]
    return a


def _index(rows: list[dict]) -> tuple[dict, dict, dict]:
    by_key = {r["key"]: r for r in rows}
    by_cp, by_c = {}, defaultdict(list)
    for r in rows:
        if r.get("record_external_identifier"):
            by_cp.setdefault((r["record_external_identifier"], r["page_stem"]), r)
            by_c[r["record_external_identifier"]].append(r)
    return by_key, by_cp, by_c


def _brief(x: dict | None, y: dict | None) -> dict:
    r = y or x
    items = item_diff(x, y)
    return {"key": r["key"], "record_external_identifier": r.get("record_external_identifier"), "page_stem": r["page_stem"],
            "a_value": x["value"] if x else None, "b_value": y["value"] if y else None,
            "diff": word_diff(x["value"] if x else None, y["value"] if y else None),
            "css_path": r.get("css_path"), "char_start": r.get("char_start"), "char_end": r.get("char_end"),
            **({"items": items} if items else {})}


def item_diff(x: dict | None, y: dict | None) -> dict | None:
    """A list row's items, paired by text within the course (property-rules spec §4.4): added and removed."""
    if (x or {}).get("items") is None and (y or {}).get("items") is None:
        return None
    a = Counter(norm(i["value"]) for i in (x or {}).get("items") or [])
    b = Counter(norm(i["value"]) for i in (y or {}).get("items") or [])
    return {"added": sorted((b - a).elements()), "removed": sorted((a - b).elements()),
            "kept": sum((a & b).values())}


def word_diff(a: str | None, b: str | None) -> list[dict]:
    """[{op: same|del|add, text}] over words (whitespace kept), for "old → new with a word diff"."""
    import difflib

    aw, bw = WORD.findall(a or ""), WORD.findall(b or "")
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=aw, b=bw, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "same", "text": "".join(aw[i1:i2])})
            continue
        if i2 > i1:
            out.append({"op": "del", "text": "".join(aw[i1:i2])})
        if j2 > j1:
            out.append({"op": "add", "text": "".join(bw[j1:j2])})
    return out
