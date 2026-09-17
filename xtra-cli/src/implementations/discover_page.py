"""What one saved page is, read from the page itself.

The crawler saved bytes. This turns one of those pages into a profile: what
it prints, which of the printed things look like field labels, which special
cases it carries, and what it is. Every literal it consults lives in
discover_rules, so the reasoning here stays readable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from implementations.discover_rules import (
    ARCHIVED_RE,
    CEU_RE,
    COREQUISITE_RE,
    COURSE_CODE_HEAD_CHARS,
    COURSE_CODE_RE,
    EMPTY_OR_ERROR_RE,
    EMPTY_PAGE_CHARS,
    LAB_CLINICAL_HOURS_RE,
    LABEL_COMPETENCY,
    LABEL_COURSE,
    LABEL_LEARNING_OPPORTUNITY,
    LECTURE_LAB_CREDIT_RE,
    MAX_FIELD_LABEL_CHARS,
    MIN_OUTCOME_ITEMS,
    MIN_PROGRAM_TERMS,
    OUTCOMES_HEADING_RE,
    PAGE_TYPE_MULTIPLE,
    PAGE_TYPE_UNKNOWN,
    POLICY_OR_DEFINITION_RE,
    PREREQ_COREQ_COMBINED_RE,
    PREREQUISITE_RE,
    PRINTED_ZERO_HOURS_RE,
    PROGRAM_URL_RE,
    RECOMMENDED_RE,
    TAB_CLASS_RE,
    TAB_ROLE_RE,
    catalog_year_value,
    collapse,
    course_block_count,
    course_codes,
    evidence,
    has_program_content,
    near_course_code,
    normalize_field_label,
    program_terms,
    url_template,
)
from implementations.engine import load_engine

_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "iframe", "template"})
_VOID_TAGS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_REPORT_HEADING_TAGS = frozenset({"h2", "h3", "h4"})
_LABEL_TAGS = frozenset({"dt", "th", "label"})
_BOLD_TAGS = frozenset({"strong", "b"})
_OUTCOME_HEADING_TAGS = _HEADING_TAGS | _LABEL_TAGS | _BOLD_TAGS
_CAPTURE_TAGS = (
    _HEADING_TAGS | _LABEL_TAGS | _BOLD_TAGS | frozenset({"title", "li"})
)
_TAB_CONTAINERS = frozenset({"nav", "ul", "ol", "div", "li", "a", "button"})


def normalized_text(html: str) -> str:
    """Visible text, via the normalizer the extractors already agree on."""
    load_engine()
    from normalize import normalize_html

    return normalize_html(html)


@dataclass
class _Element:
    tag: str
    pending_bold: list[int] = field(default_factory=list)


@dataclass
class _Capture:
    tag: str
    parts: list[str] = field(default_factory=list)


@dataclass
class PageStructure:
    """The parts of a page that only the markup can tell you."""

    title: str = ""
    h1: str = ""
    headings: list[str] = field(default_factory=list)
    label_texts: list[str] = field(default_factory=list)
    tabs_evidence: str = ""
    outcomes_evidence: str = ""


class _StructureParser(HTMLParser):
    """One pass for the title, headings, label-shaped text, and tabs.

    A bold run counts as a label when it ends with a colon or is followed by
    more text inside the same parent, which is how `<strong>Credits</strong>
    3` is written. A bold run that fills its parent is a course title, and
    course titles are not labels.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.structure = PageStructure()
        self.skip = 0
        self._elements: list[_Element] = []
        self._captures: list[_Capture] = []
        self._bolds: list[dict[str, Any]] = []
        self._outcome_heading: str | None = None
        self._outcome_items = 0

    # -- tags ---------------------------------------------------------------

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag in _SKIP_TAGS:
            self.skip += 1
            return
        if self.skip:
            return
        self._note_tabs(tag, attrs)
        if tag not in _VOID_TAGS:
            self._elements.append(_Element(tag))
        if tag in _CAPTURE_TAGS:
            self._captures.append(_Capture(tag))

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        closing: _Capture | None = None
        for index in range(len(self._captures) - 1, -1, -1):
            if self._captures[index].tag == tag:
                closing = self._captures[index]
                del self._captures[index:]
                break
        for index in range(len(self._elements) - 1, -1, -1):
            if self._elements[index].tag == tag:
                del self._elements[index:]
                break
        if closing is not None:
            self._finish(closing)

    def handle_data(self, data: str) -> None:
        if self.skip or not data:
            return
        for capture in self._captures:
            capture.parts.append(data)
        if not data.strip() or not self._elements:
            return
        parent = self._elements[-1]
        if parent.pending_bold:
            for index in parent.pending_bold:
                self._bolds[index]["followed"] = True
            parent.pending_bold.clear()

    def _note_tabs(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.structure.tabs_evidence or tag not in _TAB_CONTAINERS:
            return
        values = dict(attrs)
        role = values.get("role") or ""
        classes = values.get("class") or ""
        if TAB_ROLE_RE.search(role) or TAB_CLASS_RE.search(classes):
            hint = role or classes
            self.structure.tabs_evidence = evidence(f"<{tag}> {hint}")

    # -- what a closed element means ----------------------------------------

    def _finish(self, capture: _Capture) -> None:
        tag = capture.tag
        text = collapse("".join(capture.parts))
        if not text:
            return
        structure = self.structure
        if tag == "title" and not structure.title:
            structure.title = text
        if tag == "h1" and not structure.h1:
            structure.h1 = text
        if tag in _REPORT_HEADING_TAGS:
            structure.headings.append(text)
        if tag in _LABEL_TAGS:
            structure.label_texts.append(text)
        if tag in _BOLD_TAGS:
            self._note_bold(text)
        if tag in _OUTCOME_HEADING_TAGS:
            self._note_outcome_heading(tag, text)
        if tag == "li" and self._outcome_heading:
            self._outcome_items += 1
            if (
                self._outcome_items >= MIN_OUTCOME_ITEMS
                and not structure.outcomes_evidence
            ):
                structure.outcomes_evidence = evidence(self._outcome_heading)

    def _note_bold(self, text: str) -> None:
        index = len(self._bolds)
        followed = text.endswith(":")
        self._bolds.append({"text": text, "followed": followed})
        if not followed and self._elements:
            self._elements[-1].pending_bold.append(index)

    def _note_outcome_heading(self, tag: str, text: str) -> None:
        if OUTCOMES_HEADING_RE.search(text):
            self._outcome_heading = text
            self._outcome_items = 0
        elif tag in _HEADING_TAGS:
            self._outcome_heading = None

    def finish(self) -> PageStructure:
        self.close()
        for bold in self._bolds:
            if bold["followed"]:
                self.structure.label_texts.append(bold["text"])
        return self.structure


def parse_structure(html: str) -> PageStructure:
    parser = _StructureParser()
    parser.feed(html)
    return parser.finish()


def field_labels_of(structure: PageStructure, text: str) -> list[str]:
    """Label-shaped text from the markup and from short lines ending in a colon."""
    candidates = list(structure.label_texts)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and len(stripped) <= MAX_FIELD_LABEL_CHARS:
            candidates.append(stripped)
    labels = {
        label
        for label in (normalize_field_label(raw) for raw in candidates)
        if label
    }
    return sorted(labels)


def detect_markers(
    text: str,
    structure: PageStructure,
    *,
    blocks: int,
    visible_chars: int,
    terms: list[str],
) -> dict[str, str]:
    """Every special case this page carries, with a quote showing why."""
    markers: dict[str, str] = {}

    lecture = LECTURE_LAB_CREDIT_RE.search(text)
    if lecture is not None and near_course_code(text, lecture):
        markers["lecture_lab_credit_numbers"] = evidence(text, lecture)

    for name, rule in (
        ("lab_clinical_field_study_hours", LAB_CLINICAL_HOURS_RE),
        ("printed_zero_hours", PRINTED_ZERO_HOURS_RE),
        ("ceu", CEU_RE),
        ("prerequisite_corequisite_combined", PREREQ_COREQ_COMBINED_RE),
        ("prerequisite", PREREQUISITE_RE),
        ("corequisite", COREQUISITE_RE),
        ("recommended", RECOMMENDED_RE),
        ("archived", ARCHIVED_RE),
        ("policy_or_definition_page", POLICY_OR_DEFINITION_RE),
    ):
        match = rule.search(text)
        if match is not None:
            markers[name] = evidence(text, match)

    if structure.outcomes_evidence:
        markers["learning_outcomes"] = structure.outcomes_evidence
    if terms:
        markers["program_markers"] = ", ".join(terms)[:80]
    if structure.tabs_evidence:
        markers["tabs_present"] = structure.tabs_evidence

    year = catalog_year_value(f"{structure.title} {structure.h1}")
    if year:
        markers["catalog_year"] = year
    if blocks >= 2:
        markers["multi_course_page"] = f"{blocks} course blocks"

    error = EMPTY_OR_ERROR_RE.search(text)
    if visible_chars < EMPTY_PAGE_CHARS:
        markers["empty_or_error_page"] = f"{visible_chars} visible characters"
    elif error is not None:
        markers["empty_or_error_page"] = evidence(text, error)

    return markers


def apply_labels(
    *,
    text: str,
    structure: PageStructure,
    template: str,
    blocks: int,
    markers: dict[str, str],
    terms: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Which entities this page is about, and the evidence for each."""
    labels: list[str] = []
    fired: dict[str, str] = {}

    head = f"{structure.title} {structure.h1} {text[:COURSE_CODE_HEAD_CHARS]}"
    code_at_the_top = COURSE_CODE_RE.search(head)
    if blocks >= 1 and code_at_the_top is not None:
        labels.append(LABEL_COURSE)
        fired[LABEL_COURSE] = (
            f"{blocks} course block(s), code {code_at_the_top.group(0)} at the top"
        )
    elif blocks >= 2:
        labels.append(LABEL_COURSE)
        fired[LABEL_COURSE] = f"{blocks} course blocks"

    if len(terms) >= MIN_PROGRAM_TERMS and has_program_content(terms):
        labels.append(LABEL_LEARNING_OPPORTUNITY)
        fired[LABEL_LEARNING_OPPORTUNITY] = f"program terms: {', '.join(terms)}"
    elif PROGRAM_URL_RE.search(template):
        labels.append(LABEL_LEARNING_OPPORTUNITY)
        fired[LABEL_LEARNING_OPPORTUNITY] = f"url template {template}"

    if "learning_outcomes" in markers:
        labels.append(LABEL_COMPETENCY)
        fired[LABEL_COMPETENCY] = markers["learning_outcomes"]

    return labels, fired


def page_type_of(labels: list[str]) -> str:
    if not labels:
        return PAGE_TYPE_UNKNOWN
    if len(labels) > 1:
        return PAGE_TYPE_MULTIPLE
    return labels[0]


@dataclass
class PageProfile:
    """One line of pages.jsonl."""

    url: str
    final_url: str
    stem: str
    bytes: int
    http_status: int | None
    title: str
    h1: str
    visible_chars: int
    text_sha256: str
    url_template: str
    course_code_count: int
    course_block_count: int
    field_labels: list[str]
    headings: list[str]
    markers: dict[str, str]
    labels: list[str]
    page_type: str
    rules_fired: dict[str, str]
    duplicate_of: str | None = None
    signature: str = ""
    pattern_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "stem": self.stem,
            "bytes": self.bytes,
            "http_status": self.http_status,
            "title": self.title,
            "h1": self.h1,
            "visible_chars": self.visible_chars,
            "text_sha256": self.text_sha256,
            "duplicate_of": self.duplicate_of,
            "url_template": self.url_template,
            "course_code_count": self.course_code_count,
            "course_block_count": self.course_block_count,
            "field_labels": self.field_labels,
            "headings": self.headings,
            "markers": self.markers,
            "labels": self.labels,
            "page_type": self.page_type,
            "rules_fired": self.rules_fired,
            "signature": self.signature,
            "pattern_id": self.pattern_id,
        }


def profile_page(
    *,
    url: str,
    html: str,
    stem: str,
    final_url: str = "",
    http_status: int | None = None,
    byte_size: int | None = None,
) -> PageProfile:
    """Read one saved page. Nothing is written and nothing is fetched.

    `course_code_count` counts distinct codes, so a page that prints its own
    code six times still reports one course.
    """
    text = normalized_text(html)
    structure = parse_structure(html)
    template = url_template(url)
    blocks = course_block_count(text)
    terms = program_terms(text)
    visible_chars = len(text)
    markers = detect_markers(
        text,
        structure,
        blocks=blocks,
        visible_chars=visible_chars,
        terms=terms,
    )
    labels, fired = apply_labels(
        text=text,
        structure=structure,
        template=template,
        blocks=blocks,
        markers=markers,
        terms=terms,
    )
    return PageProfile(
        url=url,
        final_url=final_url or url,
        stem=stem,
        bytes=byte_size if byte_size is not None else len(html.encode("utf-8")),
        http_status=http_status,
        title=structure.title,
        h1=structure.h1,
        visible_chars=visible_chars,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        url_template=template,
        course_code_count=len(set(course_codes(text))),
        course_block_count=blocks,
        field_labels=field_labels_of(structure, text),
        headings=sorted(set(structure.headings)),
        markers=markers,
        labels=labels,
        page_type=page_type_of(labels),
        rules_fired=fired,
    )
