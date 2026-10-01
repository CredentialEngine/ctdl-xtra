"""Transcribe a page's printed fields from its markup.

The extractors under lib/templates read the flattened page and each one
knows one college's layout: where Brookdale puts its credits, what
Raritan calls its prerequisites. That works, and it is one file per
college for ever, because flattening the page throws away the one thing
every catalog platform does provide - it marks each field up, names the
label, and names the value beside it.

This reads those instead. Drupal writes `field__label` and `field__item`
inside a `field--name-*` div, Coursedog writes `field-label` and
`field-value`, CourseLeaf prints a course block whose title line carries
the code, the name and the credits together, and the rest of the web
writes a definition list or a table row. None of that needs to know which
college it is looking at.

It is also the only way the three entities beside Course get extracted at
all. Discovery labels credential, learning-opportunity and competency
pages, and until now nothing downstream could read one: the templates are
course templates, and a credential page has no course block for them to
find.

What it will not do is guess. A field is written down only when the page
prints it, with the element it came from recorded, so a reviewer can go
and look. A page that prints nothing this can read raises, the way the
template extractors do, rather than producing an empty record that looks
like a real one.
"""

from __future__ import annotations

from typing import Any

from implementations.discover_dom import (
    FieldPair,
    Markup,
    element_text,
    parse,
    read_field_pairs,
)
from implementations.discover_page import (
    first_paragraph,
    outcome_list,
    page_name,
    parse_structure,
)
from implementations.discover_rules import (
    COURSE_BLOCK_DESC_CLASS_RE,
    COURSE_BLOCK_TITLE_CLASS_RE,
    COURSE_FIELD_LABELS,
    ENTITY_TYPE_OF_LABEL,
    NUMERIC_FIELDS,
    collapse,
    normalize_field_label,
    split_course_title,
)
from implementations.engine import load_engine

# The entity types map_fields knows, which are the ones a record may
# carry. Discovery's labels are not all spelled the same way: what it
# calls a LearningOpportunity is a ceterms:LearningProgram.
ENTITY_COURSE = "Course"
ENTITY_CREDENTIAL = "Credential"
ENTITY_PROGRAM = "LearningProgram"
ENTITY_COMPETENCY = "Competency"

# The canonical name field for each entity, so one rule writes the page's
# own name into whichever record is being built.
NAME_FIELD = {
    ENTITY_COURSE: "course_name",
    ENTITY_CREDENTIAL: "credential_name",
    ENTITY_PROGRAM: "learning_program_name",
    ENTITY_COMPETENCY: "competency_framework_name",
}
DESCRIPTION_FIELD = {
    ENTITY_COURSE: "course_description",
    ENTITY_CREDENTIAL: "credential_description",
    ENTITY_PROGRAM: "learning_program_description",
}
ID_FIELD = {
    ENTITY_COURSE: "course_id",
    ENTITY_PROGRAM: "learning_program_id",
}


# How many fields make a record. One is the page's own name, which every
# page has and which on its own says nothing was read.
MIN_FIELDS = 2


class NothingToExtract(ValueError):
    """The page prints too little for a record."""


def entity_types_for(labels: list[str]) -> list[str]:
    """Every record a page with these labels should produce, best first.

    Usually one. A page carrying two labels produces two, because it
    really is about two things and each is published as its own entity:
    every one of the 85 program pages at Atlantic Cape prints both the
    credential and the list of what its students will be able to do, and
    a single record has nowhere to put the second.

    ENTITY_TYPE_OF_LABEL is in precedence order, so the first is the one
    the page is mainly about, and the page's own id belongs to it.
    """
    return [
        entity_type
        for label, entity_type in ENTITY_TYPE_OF_LABEL.items()
        if label in labels
    ]


def entity_type_for(labels: list[str]) -> str | None:
    """The record a page with these labels is mainly about, or None."""
    found = entity_types_for(labels)
    return found[0] if found else None


def _number(text: str) -> Any:
    """A printed number as a number, or the text when it is a range."""
    value = collapse(text)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def canonical_field(pair: FieldPair) -> str | None:
    """The canonical field this printed label is, or None.

    The label the page prints comes first, because that is what a reader
    sees. The platform's own name for the field is the fallback, for the
    fields a CMS prints with no label over them: Clean Catalog's course
    description is a div called `field--name-field-description`.
    """
    for candidate in (pair.label, pair.key):
        key = normalize_field_label(candidate) if candidate else None
        if key and key in COURSE_FIELD_LABELS:
            return COURSE_FIELD_LABELS[key]
    return None


def _draft(
    field_id: str, label: str, value: Any, excerpt: str, locator: str
) -> Any:
    load_engine()
    from transcribe_lib import FieldDraft

    return FieldDraft(
        field_id=field_id,
        canonical_label=label,
        value=value,
        raw_text=excerpt,
        excerpt=excerpt,
        locator_strategy="dom_path",
        locator_value=locator,
    )


def _collect(found: dict[str, tuple[Any, str, str]]) -> list[Any]:
    """The drafts in a stable order, numbered the way a record expects."""
    drafts = []
    for index, label in enumerate(sorted(found), start=1):
        value, excerpt, locator = found[label]
        drafts.append(_draft(f"f_{index:03d}", label, value, excerpt, locator))
    return drafts


def _from_field_pairs(
    pairs: list[FieldPair],
) -> dict[str, tuple[Any, str, str]]:
    found: dict[str, tuple[Any, str, str]] = {}
    for pair in pairs:
        label = canonical_field(pair)
        if label is None or label in found:
            continue
        value = _number(pair.value) if label in NUMERIC_FIELDS else pair.value
        found[label] = (value, pair.value, pair.path)
    return found


def _from_course_block(soup: Any) -> dict[str, tuple[Any, str, str]]:
    """The code, name and credits CourseLeaf prints on one title line."""
    found: dict[str, tuple[Any, str, str]] = {}
    title = next(
        (
            tag
            for tag in soup.find_all(True)
            if _class_named(tag, COURSE_BLOCK_TITLE_CLASS_RE)
        ),
        None,
    )
    if title is not None:
        line = element_text(title)
        code, name, credits = split_course_title(line)
        if code:
            found["course_id"] = (code, line, "p.courseblocktitle")
        if name:
            found["course_name"] = (name, line, "p.courseblocktitle")
        if credits:
            found["course_credits"] = (
                _number(credits),
                line,
                "p.courseblocktitle",
            )
    body = next(
        (
            tag
            for tag in soup.find_all(True)
            if _class_named(tag, COURSE_BLOCK_DESC_CLASS_RE)
        ),
        None,
    )
    if body is not None:
        text = element_text(body)
        if text:
            found["course_description"] = (text, text, "p.courseblockdesc")
    return found


def _class_named(tag: Any, pattern: Any) -> bool:
    value = tag.get("class")
    classes = " ".join(value) if isinstance(value, list) else (value or "")
    return bool(classes) and bool(pattern.search(classes))


def _page_fields(
    entity_type: str, markup: Markup
) -> dict[str, tuple[Any, str, str]]:
    """The name and the description every entity has, from the page itself."""
    found: dict[str, tuple[Any, str, str]] = {}
    name = page_name(markup)
    if name and entity_type in NAME_FIELD:
        found[NAME_FIELD[entity_type]] = (name, name, "h1")
    intro = first_paragraph(markup.content_text)
    if intro and entity_type in DESCRIPTION_FIELD:
        found[DESCRIPTION_FIELD[entity_type]] = (intro, intro, "main > p")
    return found


def extract_fields(entity_type: str, html: str) -> list[Any]:
    """Every field this page prints for this entity, read from its markup.

    Raises NothingToExtract when the page prints none, because a record
    with nothing in it is worse than no record: it looks extracted.
    """
    soup = parse(html)
    markup = parse_structure(html)
    if entity_type == ENTITY_COMPETENCY:
        return _competency_drafts(markup)

    # Strongest source first, and each one fills only what the one before
    # it left empty. A field the page labelled says what it is; the course
    # block is what CourseLeaf gives instead of labelled fields; the page
    # itself is the last resort, because the h1 of a CourseLeaf subject
    # page is the subject's name, not the course's.
    sources: list[dict[str, tuple[Any, str, str]]] = []
    if entity_type == ENTITY_COURSE:
        sources = [
            _from_field_pairs(read_field_pairs(soup)),
            _from_course_block(soup),
        ]
    sources.append(_page_fields(entity_type, markup))
    found: dict[str, tuple[Any, str, str]] = {}
    for source in sources:
        for label, value in source.items():
            found.setdefault(label, value)
    # The page's own name is not a record. Every page has one, so a
    # record holding nothing else is an empty record that looks extracted,
    # which is the one thing this must not produce.
    if len(found) < MIN_FIELDS:
        raise NothingToExtract(
            f"the page prints {len(found)} field(s) this can read from its "
            f"markup, fewer than the {MIN_FIELDS} a record needs"
        )
    return _collect(found)


def _competency_drafts(markup: Markup) -> list[Any]:
    """One draft per outcome the page lists, plus what the list is called."""
    lead_in, items = outcome_list(
        markup.content_text,
        headings={
            *markup.content_headings,
            *([markup.h1] if markup.h1 else []),
        },
        list_items=set(markup.list_items),
    )
    if not items:
        raise NothingToExtract("the page lists no learning outcome")
    drafts = []
    name = page_name(markup)
    if name:
        drafts.append(
            _draft("f_001", "competency_framework_name", name, name, "h1")
        )
    for index, item in enumerate(items, start=len(drafts) + 1):
        drafts.append(
            _draft(
                f"f_{index:03d}",
                "competency_text",
                item,
                item,
                f"outcome list under {lead_in[:40]!r}",
            )
        )
    return drafts
