"""A spread sample of a rule's rows: group them so a reviewer sees as many kinds of value as possible, then deal one
row from each group in turn (spec §7.2 "rows without signals are sampled").

How rows are grouped, per rule:
- a field with few distinct values (Language, Life Cycle Status Type): one group per value, rarest first;
- a structured field (codes, URLs: few distinct shapes, letters → A and digits → 9, `ABDY 112` → `A 9`): one group
  per shape, rarest first;
- free text (a description, a name): five word-count percentile buckets, so short, typical and very long values
  all come up;
- a field's empty values: one group of their own;
- a record locator: the page each course was found on when pages hold several courses, else the course subject;
- a page rule: the URL pattern when there are several, else percentile buckets of the courses found on the page,
  else the subject in the page title.

Within a group rows go round the course subjects (`ABDY`, `ACCT`, …) so one department doesn't fill it; inside a
subject the order is the caller's seeded random order. Pure functions, so they are tested without a catalog.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from urllib.parse import urlparse

FEW_VALUES = 30             # a field with at most this many distinct values is grouped by value; one with at most
                            # this many distinct shapes is structured (codes, URLs) and grouped by shape
BUCKETS = 5


def words(v: str | None) -> int:
    return len((v or "").split())


def shape(v: str | None) -> str:
    """Letters → A, digits → 9, runs collapsed: 'ABDY 112' → 'A 9', '3.0 units' → '9.9 A'."""
    s = re.sub(r"[^\W\d_]+", "A", v or "")
    return re.sub(r"\d+", "9", s).strip()


def subject(row: dict) -> str:
    """ABDY for ABDY112; for a page row, the first word of its title."""
    m = re.match(r"[A-Za-z]+", row.get("course_key") or row.get("value") or "")
    return m.group(0).upper() if m else ""


def url_pattern(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if parts:
        parts[-1] = "*"
    return "/" + "/".join(re.sub(r"\d+", "9", p) for p in parts)


def buckets(sizes: dict[str, int], unit: str, k: int = BUCKETS) -> tuple[dict[str, str], list[str]]:
    """Percentile buckets of a number per row ('12–50 words (percentile 0–21)'), smallest first. Ties stay together, so
    a bucket's share is the real share of rows in it."""
    if not sizes:
        return {}, []
    s = sorted(sizes.values())
    n = len(s)
    edges = sorted({s[max(0, (i * n) // k - 1)] for i in range(1, k)} | {s[-1]})
    bounds, lo = [], s[0]
    for e in edges:
        if e >= lo:
            bounds.append((lo, e))
            lo = e + 1
    names, below = [], 0
    for a, b in bounds:
        inside = sum(1 for x in s if a <= x <= b)
        span = f"{a:,}–{b:,}" if a != b else f"{a:,}"
        names.append(f"{span} {unit} (percentile {round(100 * below / n)}–{round(100 * (below + inside) / n)})")
        below += inside
    label = {key: names[next(i for i, (_, b) in enumerate(bounds) if v <= b)] for key, v in sizes.items()}
    return label, names


def _by_count(label: dict[str, str]) -> list[str]:
    """Group labels, smallest group first; equal sizes in a fixed shuffled order."""
    c = Counter(label.values())
    return sorted(c, key=lambda g: (c[g], hashlib.sha1(g.encode()).hexdigest()))


def groups(kind: str, rows: list[dict], courses_on_page: dict[str, int] | None = None
           ) -> tuple[str, dict[str, str], list[str]]:
    """(what the rows are grouped by, row key → group label, group labels in dealing order)."""
    if kind == "field":
        found = [r for r in rows if r["status"] == "found" and (r["value"] or "").strip()]
        distinct = Counter((r["value"] or "").strip() for r in found)
        shapes = {shape(r["value"]) for r in found}
        if len(distinct) <= FEW_VALUES:
            by = "value: one group per distinct value, rarest first"
            label = {r["key"]: f"“{(r['value'] or '').strip()[:40]}”" for r in found}
            order = _by_count(label)
        elif len(shapes) <= FEW_VALUES:
            by = "shape: letters → A, digits → 9, rarest shape first"
            label = {r["key"]: f"shape “{shape(r['value'])[:40]}”" for r in found}
            order = _by_count(label)
        else:
            by = "length: percentiles of the word count"
            label, order = buckets({r["key"]: words(r["value"]) for r in found}, "words")
        empty = {r["key"]: "no value" for r in rows if r["key"] not in label}
        return by, label | empty, order + (["no value"] if empty else [])
    if kind == "locator":
        per = Counter(r["page_stem"] for r in rows)
        if sorted(per.values())[len(per) // 2] > 1 if per else False:
            label = {r["key"]: f"page “{(r['context'] or r['page_stem'])[:60]}”" for r in rows}
            return "page: the page each course was found on", label, _by_count(label)
        label = {r["key"]: f"subject {subject(r) or '—'}" for r in rows}
        return "subject: the letters of the course code", label, _by_count(label)
    label = {r["key"]: url_pattern(r["context"] or "") for r in rows}
    if len(set(label.values())) > 1:
        return "URL pattern of the page", label, _by_count(label)
    on_page = {r["key"]: (courses_on_page or {}).get(r["page_stem"], 0) for r in rows}
    if len(set(on_page.values())) > 1:
        label, order = buckets(on_page, "courses on the page")
        return "courses found on the page: percentiles", label, order
    label = {r["key"]: f"subject {subject(r) or '—'}" for r in rows}
    return "subject: the first word of the page title", label, _by_count(label)


def spread(rows: list[dict], label: dict[str, str], order: list[str], rnd: Callable[[dict], str]) -> list[dict]:
    """Deal one row from each group in turn; within a group, one from each course subject in turn."""
    by_group: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=rnd):
        by_group[label[r["key"]]].append(r)
    queues = []
    for g in order:
        if g not in by_group:
            continue
        by_subj: dict[str, list[dict]] = defaultdict(list)
        for r in by_group[g]:
            by_subj[subject(r)].append(r)
        queues.append(_round_robin(list(by_subj.values())))
    return _round_robin(queues)


def _round_robin(lists: list[list[dict]]) -> list[dict]:
    out, i = [], 0
    while True:
        took = False
        for lst in lists:
            if i < len(lst):
                out.append(lst[i])
                took = True
        if not took:
            return out
        i += 1
