"""The things a page names, pulled out and typed.

Discovery already decides what a page *is*. This says what it *names*:
the award it grants, the courses it lists, the credits it prints, the
terms those courses run in, whose page it is, and the work it leads to.

    AWARD        Associate in Applied Science
    COURSE_CODE  ENGL 101
    CREDITS      3 credits            -> 3 to 3
    TERM         Fall 2026
    ORG          Atlantic Cape Community College
    OCCUPATION   Registered Nurse

Nothing here is a model, and nothing is fetched or downloaded. Every span
is found by the vocabulary in discover_rules, which is the same
vocabulary the labels are decided by, so an entity a reviewer disagrees
with is one line to find and one line to change. A statistical recogniser
would give ORG and DATE and never AWARD or COURSE_CODE, which are the two
a credential catalog is published for.

Two things make this worth more than running the regexes over the page.

The first is that it reads the page's own content. `read_markup` has
already dropped the menus, and the menu is where a catalog prints
"Degrees & Certificates" on all 948 pages - so an award found here is one
the page is about. The second is that the markup is believed before the
prose, the same way the labels believe it: the courses a page describes
are the ones the platform marked up as descriptions, and the credits are
the ones it marked up as a credits field, whatever the flattened text
reads like.

An occupation is the one kind with no vocabulary to reuse, and it is
found the way the contact-line rule is: two signals, never one. A job
title is a head noun from a gazetteer, and it counts only on a line that
introduces work ("prepares students for careers as...") or under a
heading that stands over a list of jobs. The head noun alone reads
"Nurse Education" as a nurse and every department chair as an officer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from implementations.discover_dom import Markup
from implementations.discover_rules import (
    COURSE_CODE_RE,
    CREDIT_VALUE_RE,
    ENTITY_AWARD,
    ENTITY_COURSE_CODE,
    ENTITY_CREDITS,
    ENTITY_KINDS,
    ENTITY_LIMIT,
    ENTITY_OCCUPATION,
    ENTITY_ORGANIZATION,
    ENTITY_QUOTE_CHARS,
    ENTITY_TERM,
    OUTCOME_LEAD_GAP_LINES,
    TERM_HEADING_RE,
    catalog_year_value,
    collapse,
    credit_amounts,
    heading_body,
    is_occupation_context,
    named_awards,
    names_a_career_list,
    normalize_course_code,
    occupation_titles,
    occupation_value,
    organization_names,
    quote_around,
    term_values,
)

# The class a platform stamps on the field holding a credits value, for
# the pages that print the number nowhere a sentence can reach it.
_CREDIT_FIELD_WORDS = ("credit", "unit", "hour")
# The class naming the field that holds the award: Clean Catalog's
# `field--name-field-degree-type`, Coursedog's `degree-type`.
_AWARD_FIELD_WORDS = ("degree type", "degree-type", "award", "credential")


@dataclass(frozen=True)
class Entity:
    """One thing a page names, and where it says it.

    `text` is the span as printed, `value` is it normalized so two
    spellings of one thing count once, and `quote` is the words around it
    so a reviewer never has to open the page to judge it.
    """

    kind: str
    text: str
    value: str
    quote: str
    source: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "text": self.text,
            "value": self.value,
            "quote": self.quote,
            "source": self.source,
        }


def _quote(line: str) -> str:
    return collapse(line)[:ENTITY_QUOTE_CHARS]


class _Collector:
    """Entities in the order found, with each value kept once per kind.

    First writer wins, so the markup's reading of a value keeps its place
    when the prose finds the same one further down. That is the same rule
    the labels follow, stated once here rather than at every call.
    """

    def __init__(self) -> None:
        self._found: list[Entity] = []
        self._seen: set[tuple[str, str]] = set()

    def add(
        self, kind: str, text: str, value: str, quote: str, source: str
    ) -> None:
        text = collapse(text)
        if not text or not value:
            return
        key = (kind, value.lower())
        if key in self._seen:
            return
        self._seen.add(key)
        self._found.append(Entity(kind, text, value, _quote(quote), source))

    def entities(self) -> list[Entity]:
        """Every entity found, capped per kind so a report stays readable."""
        kept: list[Entity] = []
        counts: dict[str, int] = {}
        for entity in self._found:
            counts[entity.kind] = counts.get(entity.kind, 0) + 1
            if counts[entity.kind] <= ENTITY_LIMIT:
                kept.append(entity)
        return kept


def _field_matching(markup: Markup, words: tuple[str, ...]) -> list[Any]:
    """The page's field pairs whose label or platform key names one of these."""
    found = []
    for pair in markup.field_pairs:
        haystack = f"{pair.label} {pair.key}".lower()
        if any(word in haystack for word in words):
            found.append(pair)
    return found


def _read_awards(markup: Markup, into: _Collector) -> None:
    """The award the page grants: the field first, then its own content.

    A platform that marks the award up has answered outright. Atlantic
    Cape badges every program with `field--name-field-degree-type`, and
    reading that field is why "Professional Series", which carries no
    award noun, is found at all.
    """
    for pair in _field_matching(markup, _AWARD_FIELD_WORDS):
        value = collapse(pair.value)
        if value:
            into.add(
                ENTITY_AWARD, value, value, f"{pair.label} {value}", "field"
            )
    declared = markup.declaration()
    if declared is not None and declared.award:
        into.add(
            ENTITY_AWARD,
            declared.award,
            collapse(declared.award),
            declared.quote,
            f"declared in {declared.source}",
        )
    content = markup.content_text
    for text in named_awards(content):
        into.add(
            ENTITY_AWARD,
            text,
            collapse(text),
            quote_around(content, text),
            "content",
        )


def _read_course_codes(markup: Markup, into: _Collector) -> None:
    """The courses the page names, the ones it describes first.

    A marked-up course block is a course the page is about. A code in a
    requirement table is a course the page points at. Both are named, and
    the source says which, because on a program page the difference is
    the whole question.
    """
    for block in markup.course_blocks:
        into.add(
            ENTITY_COURSE_CODE,
            block.code,
            normalize_course_code(block.code),
            block.quote,
            "course block",
        )
    content = markup.content_text
    for match in COURSE_CODE_RE.finditer(content):
        text = match.group(0)
        code = normalize_course_code(text)
        into.add(
            ENTITY_COURSE_CODE,
            text,
            code,
            _around(content, match.start(), match.end()),
            "reference" if code in markup.reference_codes else "content",
        )


def _read_credits(markup: Markup, into: _Collector) -> None:
    """Every credits value printed, with the number read out of it."""
    for pair in _field_matching(markup, _CREDIT_FIELD_WORDS):
        value = collapse(pair.value)
        low, high = credit_amounts(value)
        if low:
            into.add(
                ENTITY_CREDITS,
                value,
                low if low == high else f"{low}-{high}",
                f"{pair.label} {value}",
                "field",
            )
    content = markup.content_text
    for match in CREDIT_VALUE_RE.finditer(content):
        text = match.group(0)
        low, high = credit_amounts(text)
        if not low:
            continue
        into.add(
            ENTITY_CREDITS,
            text,
            low if low == high else f"{low}-{high}",
            _around(content, match.start(), match.end()),
            "content",
        )


def _read_terms(markup: Markup, into: _Collector) -> None:
    """The terms the page names, and the catalog year it belongs to.

    A term heading counts only as a heading: "Fall" appears in every
    refund schedule, and TERM_HEADING_RE is anchored for that reason.
    """
    for heading in markup.content_headings:
        body = heading_body(heading)
        if TERM_HEADING_RE.match(body):
            into.add(ENTITY_TERM, body, collapse(body), heading, "heading")
    content = markup.content_text
    for text in term_values(content):
        into.add(
            ENTITY_TERM, text, text, quote_around(content, text), "content"
        )
    year = catalog_year_value(f"{markup.title} {markup.h1}")
    if year:
        into.add(
            ENTITY_TERM,
            year,
            year,
            f"{markup.title} {markup.h1}",
            "catalog year",
        )


def _read_organizations(markup: Markup, into: _Collector) -> None:
    """Whose page this is: the site's own name, then any it names."""
    if markup.site_name:
        into.add(
            ENTITY_ORGANIZATION,
            markup.site_name,
            markup.site_name,
            markup.site_name,
            "site name",
        )
    content = markup.content_text
    for name in organization_names(content):
        into.add(
            ENTITY_ORGANIZATION,
            name,
            name,
            quote_around(content, name),
            "content",
        )


def _career_list_lines(lines: list[str], list_items: set[str]) -> list[str]:
    """The lines under a heading that stands over a list of jobs.

    The same shape as a list of learning outcomes: a heading, then the
    items directly after it, ending at the first line that is not one. A
    blank run longer than the outcome rules allow ends it too, so a
    heading with the list on the far side of a paragraph is not read as
    naming everything below it.
    """
    found: list[str] = []
    for index, line in enumerate(lines):
        if not names_a_career_list(line):
            continue
        gap = 0
        for following in lines[index + 1 :]:
            if following in list_items or len(following.split()) <= 6:
                found.append(following)
                gap = 0
                continue
            if found:
                break
            gap += 1
            if gap > OUTCOME_LEAD_GAP_LINES:
                break
    return found


def _read_occupations(markup: Markup, into: _Collector) -> None:
    """The work the page says its graduates go into.

    Two signals, never one. A head noun counts on a line that introduces
    work, or on a line listed under a heading that stands over jobs.
    """
    lines = markup.content_text.splitlines()
    listed = set(
        _career_list_lines(lines, set(markup.list_items))
        + _career_list_lines(markup.content_headings, set(markup.list_items))
    )
    for line in lines:
        if not (is_occupation_context(line) or line in listed):
            continue
        for title in occupation_titles(line):
            value = occupation_value(title)
            if value:
                into.add(
                    ENTITY_OCCUPATION,
                    title,
                    value,
                    line,
                    "named in a list" if line in listed else "named in a cue",
                )


def _around(text: str, start: int, end: int) -> str:
    """The words around a span, so a reviewer sees where it was found."""
    return text[max(0, start - 20) : end + 40]


def read_entities(markup: Markup) -> list[Entity]:
    """Every entity one page names, read from its markup and its content."""
    into = _Collector()
    _read_awards(markup, into)
    _read_course_codes(markup, into)
    _read_credits(markup, into)
    _read_terms(markup, into)
    _read_organizations(markup, into)
    _read_occupations(markup, into)
    return into.entities()


def entities_by_kind(entities: list[Entity]) -> dict[str, list[str]]:
    """The values found, by kind, for the one line a page gets in a report."""
    found: dict[str, list[str]] = {kind: [] for kind in ENTITY_KINDS}
    for entity in entities:
        found[entity.kind].append(entity.value)
    return {kind: values for kind, values in found.items() if values}
