"""Loads the rule registry and applies a rule to a piece of text, counting as it goes (EX5)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Hit:
    """One match of one rule. Positions are in the document's text, not the scope's."""

    rule: "Rule"
    start: int
    end: int
    quote: str
    groups: dict[str, str | None]
    spans: dict[str, tuple[int, int]]
    match_start: int
    match_end: int

    def says(self) -> str:
        shown = {k: (v or "") for k, v in self.groups.items()}
        shown["quote"] = " ".join(self.quote.replace(" ", " ").split())
        return self.rule.says.format(**shown)


@dataclass
class Rule:
    name: str
    feeds: str
    where: str
    where_plain: str
    pattern: str
    description: str
    says: str
    expect: str = "some"
    near_miss: str | None = None
    extra: dict = field(default_factory=dict)
    matched: list[str] = field(default_factory=list)
    not_matched: list[str] = field(default_factory=list)
    near_misses: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._re = re.compile(self.pattern)
        self._near = re.compile(self.near_miss) if self.near_miss else None

    def find_all(self, text: str, offset: int = 0) -> list[Hit]:
        hits = []
        for m in self._re.finditer(text):
            group = "quote" if "quote" in m.groupdict() else 0
            spans = {
                name: (m.start(name) + offset, m.end(name) + offset)
                for name, value in m.groupdict().items()
                if value is not None
            }
            hits.append(
                Hit(
                    rule=self,
                    start=m.start(group) + offset,
                    end=m.end(group) + offset,
                    quote=m.group(group),
                    groups=m.groupdict(),
                    spans=spans,
                    match_start=m.start() + offset,
                    match_end=m.end() + offset,
                )
            )
        return hits

    def apply(self, text: str, offset: int, subject: str) -> list[Hit]:
        """Apply to one course (or page), and remember whether it matched."""
        hits = self.find_all(text, offset)
        if hits:
            self.matched.append(subject)
        else:
            self.not_matched.append(subject)
            if self._near:
                near = self._near.search(text)
                if near:
                    lo, hi = max(0, near.start() - 60), near.end() + 60
                    self.near_misses.append(
                        {"where": subject, "text": " ".join(text[lo:hi].replace(" ", " ").split())}
                    )
        return hits

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "feeds": self.feeds,
            "where": self.where,
            "wherePlain": self.where_plain,
            "pattern": self.pattern,
            "description": self.description,
            "expect": self.expect,
            **({"leftOutReason": self.extra["left_out_reason"]} if "left_out_reason" in self.extra else {}),
        }


@dataclass
class Table:
    name: str
    feeds: str
    scheme: str
    description: str
    rows: dict[str, dict]
    matched: dict[str, int] = field(default_factory=dict)
    not_matched: dict[str, list[str]] = field(default_factory=dict)

    def look_up(self, wording: str, subject: str) -> dict | None:
        row = self.rows.get(wording)
        if row is None:
            self.not_matched.setdefault(wording, []).append(subject)
            return None
        self.matched[wording] = self.matched.get(wording, 0) + 1
        return row

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "feeds": self.feeds,
            "scheme": self.scheme,
            "description": self.description,
            "rows": [
                {
                    "wording": w,
                    "concept": r["concept"],
                    "because": r["because"],
                    "loses": r.get("loses", ""),
                    "reviewedByAPerson": bool(r.get("reviewed_by_a_person")),
                }
                for w, r in self.rows.items()
            ],
        }


@dataclass
class Phrase:
    text: str
    role: str  # "condition" or "modifier"


@dataclass
class Registry:
    rules: dict[str, Rule]
    tables: dict[str, Table]
    phrases: list[Phrase]

    def rule(self, name: str) -> Rule:
        return self.rules[name]


_KNOWN = {"name", "feeds", "where", "where_plain", "pattern", "description", "says", "expect", "near_miss"}


def load_registry(path: Path) -> Registry:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    rules = {}
    for entry in data["rule"]:
        known = {k: v for k, v in entry.items() if k in _KNOWN}
        extra = {k: v for k, v in entry.items() if k not in _KNOWN}
        rules[entry["name"]] = Rule(**known, extra=extra)
    tables = {}
    for name, t in data.get("table", {}).items():
        tables[name] = Table(
            name=name,
            feeds=t["feeds"],
            scheme=t["scheme"],
            description=t["description"],
            rows={row["wording"]: row for row in t["row"]},
        )
    phrases = [Phrase(p["text"], p["role"]) for p in data.get("phrase", [])]
    return Registry(rules, tables, phrases)
